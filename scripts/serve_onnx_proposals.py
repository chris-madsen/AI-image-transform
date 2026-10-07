"""Serve a pinned local ONNX matting proposal over HTTP.

This adapter is intended for the Windows DirectML inference host. It never
downloads weights and never promotes its alpha to an authoritative result. The
Linux service consumes the same typed proposal contract as the PyTorch
deployment adapter.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from PIL import Image

from printify_artwork_cleaner.adapters.model_proposals import derive_mask_tuning
from printify_artwork_cleaner.domain.image_math import canonical_rgba_png_bytes


DIRECTML_PROVIDER = "DmlExecutionProvider"
CPU_PROVIDER = "CPUExecutionProvider"
SUPPORTED_INPUT_SIZES = (1024, 2048)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_hash(value: str, name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise RuntimeError(f"{name} must be a lowercase SHA-256")
    return normalized


def _encode_mask(mask: np.ndarray) -> str:
    stream = io.BytesIO()
    Image.fromarray(np.asarray(mask, dtype=np.uint8), mode="L").save(stream, format="PNG", optimize=False)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _decode_source(payload: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="request body must be a valid image") from exc


def _preprocess(source: np.ndarray, input_size: int) -> np.ndarray:
    """Create a deterministic NCHW float32 RGB tensor for the ONNX contract."""
    image = Image.fromarray(np.asarray(source, dtype=np.uint8), mode="RGBA").convert("RGB")
    resized = np.asarray(image.resize((input_size, input_size), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    normalized = (resized - np.asarray([0.485, 0.456, 0.406], dtype=np.float32)) / np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
    return np.transpose(normalized, (2, 0, 1))[None, ...].astype(np.float32, copy=False)


def _sigmoid(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(value, dtype=np.float32), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _squeeze_output(output: np.ndarray) -> np.ndarray:
    value = np.asarray(output)
    value = np.squeeze(value)
    if value.ndim != 2:
        raise RuntimeError(f"ONNX output must reduce to one HxW plane, got {value.shape}")
    return value.astype(np.float32, copy=False)


def _postprocess(output: np.ndarray, source_size: tuple[int, int], output_mode: str) -> np.ndarray:
    values = _squeeze_output(output)
    if output_mode == "logits":
        values = _sigmoid(values)
    elif output_mode not in {"alpha", "foreground"}:
        raise RuntimeError("MODEL_OUTPUT_MODE must be logits, alpha or foreground")
    if float(np.nanmax(values)) <= 1.0 + 1e-5:
        values = values * 255.0
    alpha = np.uint8(np.clip(np.nan_to_num(values, nan=0.0, posinf=255.0, neginf=0.0), 0.0, 255.0))
    width, height = source_size
    return np.asarray(Image.fromarray(alpha, mode="L").resize((width, height), Image.Resampling.LANCZOS), dtype=np.uint8)


def _select_providers(available: tuple[str, ...] | list[str], require_directml: bool) -> tuple[str, ...]:
    present = tuple(available)
    if require_directml and DIRECTML_PROVIDER not in present:
        raise RuntimeError(f"{DIRECTML_PROVIDER} is unavailable; refusing CPU-only production mode")
    selected = tuple(provider for provider in (DIRECTML_PROVIDER, CPU_PROVIDER) if provider in present)
    if not selected:
        raise RuntimeError(f"ONNX Runtime exposes no supported providers: {present}")
    return selected


class OnnxProposalModel:
    """Thread-safe, one-request-at-a-time ONNX proposal runner."""

    def __init__(self) -> None:
        import onnxruntime as ort

        self.ort = ort
        self.kind = _required("MODEL_KIND")
        self.model_path = Path(_required("MODEL_PATH"))
        self.model_version = _required("MODEL_VERSION")
        self.model_license = _required("MODEL_LICENSE")
        self.weights_sha256 = _validate_hash(_required("MODEL_WEIGHTS_SHA256"), "MODEL_WEIGHTS_SHA256")
        actual_hash = _sha256(self.model_path)
        if actual_hash != self.weights_sha256:
            raise RuntimeError(f"weights hash mismatch: expected {self.weights_sha256}, got {actual_hash}")
        self.input_size = int(os.getenv("MODEL_INPUT_SIZE", "1024"))
        if self.input_size not in SUPPORTED_INPUT_SIZES:
            raise RuntimeError(f"MODEL_INPUT_SIZE must be one of {SUPPORTED_INPUT_SIZES}")
        self.output_mode = os.getenv("MODEL_OUTPUT_MODE", "logits").lower()
        self.require_directml = os.getenv("MODEL_REQUIRE_DIRECTML", "0").lower() in {"1", "true", "yes"}
        available = tuple(ort.get_available_providers())
        self.providers = _select_providers(available, self.require_directml)
        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern = False
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.model_path), sess_options=options, providers=list(self.providers))
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self._validate_model_shape(self.session.get_inputs()[0].shape)
        self.lock = threading.Lock()

    def _validate_model_shape(self, shape: list[Any] | tuple[Any, ...]) -> None:
        fixed_height = shape[-2] if len(shape) >= 4 and isinstance(shape[-2], int) else None
        fixed_width = shape[-1] if len(shape) >= 4 and isinstance(shape[-1], int) else None
        if fixed_height is not None and fixed_width is not None and (fixed_height, fixed_width) != (self.input_size, self.input_size):
            raise RuntimeError(f"MODEL_INPUT_SIZE={self.input_size} does not match ONNX input shape {shape}")

    def predict(self, source: np.ndarray) -> tuple[np.ndarray, float]:
        tensor = _preprocess(source, self.input_size)
        started = time.perf_counter()
        with self.lock:
            output = self.session.run([self.output_name], {self.input_name: tensor})[0]
        alpha = _postprocess(output, (source.shape[1], source.shape[0]), self.output_mode)
        return alpha, time.perf_counter() - started

    def response(self, source: np.ndarray) -> dict[str, Any]:
        source_hash = hashlib.sha256(canonical_rgba_png_bytes(source)).hexdigest()
        alpha, elapsed = self.predict(source)
        protection = np.where(alpha >= 192, 255, 0).astype(np.uint8)
        uncertainty = np.uint8(np.clip(255 - np.abs(alpha.astype(np.int16) * 2 - 255), 0, 255))
        proposal_hash = hashlib.sha256(alpha.tobytes() + (protection > 0).tobytes() + uncertainty.tobytes()).hexdigest()
        return {
            "alpha_png_base64": _encode_mask(alpha),
            "protection_png_base64": _encode_mask(protection),
            "uncertainty_png_base64": _encode_mask(uncertainty),
            "source_sha256": source_hash,
            "model": self.kind,
            "version": self.model_version,
            "license": self.model_license,
            "weights_sha256": self.weights_sha256,
            "proposal_sha256": proposal_hash,
            "inference_seconds": elapsed,
            "provider": self.providers[0],
            "input_size": self.input_size,
            "mask_tuning": asdict(derive_mask_tuning(source, alpha, source_hash)),
            "visual_quality": {
                "reference_id": "model-preflight-not-approval",
                "overall_score": 0.0,
                "subject_integrity": 0.0,
                "intentional_detail_score": 0.0,
                "edge_naturalness": 0.0,
                "artifact_free_score": 0.0,
                "confidence": 0.0,
                "source_sha256": source_hash,
                "checkpoint_sha256": "",
                "reviewer_notes": ["ONNX segmentation proposal only", "requires independent checkpoint review"],
            },
        }


_model: OnnxProposalModel | None = None


def _get_model() -> OnnxProposalModel:
    global _model
    if _model is None:
        _model = OnnxProposalModel()
    return _model


@asynccontextmanager
async def lifespan(_: FastAPI):
    _get_model()
    yield


def build_app() -> FastAPI:
    app = FastAPI(title="Local ONNX proposal adapter", lifespan=lifespan)

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        model = _get_model()
        return {
            "status": "ok",
            "model_kind": model.kind,
            "model_version": model.model_version,
            "weights_sha256": model.weights_sha256,
            "providers": list(model.providers),
            "active_provider": model.providers[0],
            "input_size": model.input_size,
            "execution_mode": "ORT_SEQUENTIAL",
            "memory_pattern": False,
        }

    @app.post("/v1/proposal")
    async def proposal(request: Request) -> dict[str, Any]:
        return _get_model().response(_decode_source(await request.body()))

    return app


app = build_app()
