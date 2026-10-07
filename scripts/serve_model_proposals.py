"""Serve pinned BiRefNet HR-matting or BEN2 proposals over HTTP.

This is a deployment-only adapter.  The repository's normal service does not
download model weights and does not import torch from the domain core.  Start
one process per model, point the service at both processes, and keep the
weights outside Git.

The endpoint deliberately returns a low-confidence visual-quality assessment.
The segmentation model is a proposal source, not an aesthetic reviewer.  A
separate multimodal reviewer must inspect Photopea checkpoints before a job
can become ``passed``.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from PIL import Image
from torchvision import transforms

from printify_artwork_cleaner.domain.image_math import canonical_rgba_png_bytes
from printify_artwork_cleaner.adapters.model_proposals import derive_mask_tuning


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


def _model_file(path: Path) -> Path:
    if path.is_file():
        return path
    candidates = tuple(sorted(path.glob("*.safetensors")))
    if not candidates:
        raise RuntimeError(f"no safetensors model file found under {path}")
    return candidates[0]


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


def _dynamic_tuning(source: np.ndarray, alpha: np.ndarray, source_sha256: str) -> dict[str, Any]:
    """Derive bounded per-artwork evidence from the current source/proposal.

    These values are diagnostics for the core's perimeter renderer.  They are
    not global defaults and cannot authorize a job without the reviewer gate.
    """

    return asdict(derive_mask_tuning(source, alpha, source_sha256))


def _visual_preflight(alpha: np.ndarray, source_sha256: str) -> dict[str, Any]:
    partial = float(np.count_nonzero((alpha > 0) & (alpha < 255))) / float(alpha.size)
    uncertainty = float(np.clip(1.0 - partial * 2.0, 0.0, 1.0))
    return {
        "reference_id": "model-preflight-not-approval",
        "overall_score": 0.0,
        "subject_integrity": uncertainty,
        "intentional_detail_score": 0.0,
        "edge_naturalness": 0.0,
        "artifact_free_score": 0.0,
        "confidence": 0.0,
        "source_sha256": source_sha256,
        "checkpoint_sha256": "",
        "reviewer_notes": [
            "segmentation proposal only",
            "requires independent multimodal checkpoint review",
        ],
    }


class ProposalModel:
    def __init__(self) -> None:
        self.kind = _required("MODEL_KIND").lower()
        self.model_path = Path(_required("MODEL_PATH"))
        self.model_version = _required("MODEL_VERSION")
        self.model_license = _required("MODEL_LICENSE")
        self.weights_sha256 = _required("MODEL_WEIGHTS_SHA256").lower()
        if len(self.weights_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.weights_sha256):
            raise RuntimeError("MODEL_WEIGHTS_SHA256 must be a lowercase SHA-256")
        actual_hash = _sha256(_model_file(self.model_path))
        if actual_hash != self.weights_sha256:
            raise RuntimeError(f"weights hash mismatch: expected {self.weights_sha256}, got {actual_hash}")
        self.device = torch.device(os.getenv("MODEL_DEVICE", "cpu"))
        self.input_size = int(os.getenv("MODEL_INPUT_SIZE", "1024"))
        self.lock = threading.Lock()
        self.model = self._load()

    def _load(self) -> Any:
        if self.kind == "birefnet":
            from transformers import AutoModelForImageSegmentation

            return AutoModelForImageSegmentation.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                local_files_only=True,
            ).to(self.device).eval()
        if self.kind == "ben2":
            from ben2 import BEN_Base

            return BEN_Base.from_pretrained(str(self.model_path)).to(self.device).eval()
        raise RuntimeError("MODEL_KIND must be birefnet or ben2")

    def _predict_birefnet(self, source: Image.Image) -> np.ndarray:
        transform = transforms.Compose(
            [
                transforms.Resize((self.input_size, self.input_size), interpolation=transforms.InterpolationMode.BILINEAR),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        tensor = transform(source.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            output = self.model(tensor)
            logits = output[-1] if isinstance(output, (tuple, list)) else getattr(output, "logits", output)
            alpha = torch.sigmoid(logits)[0, 0].detach().cpu().numpy()
        return np.asarray(Image.fromarray(np.uint8(np.clip(alpha * 255, 0, 255)), mode="L").resize(source.size, Image.Resampling.LANCZOS), dtype=np.uint8)

    def _predict_ben2(self, source: Image.Image) -> np.ndarray:
        with torch.inference_mode():
            result = self.model.inference(source.convert("RGB"), refine_foreground=False)
        return np.asarray(result.convert("RGBA"), dtype=np.uint8)[..., 3]

    def predict(self, source: np.ndarray) -> tuple[np.ndarray, float]:
        image = Image.fromarray(source, mode="RGBA")
        started = time.perf_counter()
        with self.lock:
            alpha = self._predict_birefnet(image) if self.kind == "birefnet" else self._predict_ben2(image)
        return alpha, time.perf_counter() - started

    def response(self, source: np.ndarray) -> dict[str, Any]:
        canonical = canonical_rgba_png_bytes(source)
        source_sha256 = hashlib.sha256(canonical).hexdigest()
        alpha, elapsed = self.predict(source)
        # Protection is deliberately conservative: it marks confident model
        # foreground for downstream protection, while uncertainty remains
        # available for the reviewer and no model output is silently promoted.
        protection = np.where(alpha >= 192, 255, 0).astype(np.uint8)
        uncertainty = np.uint8(np.clip(255 - np.abs(alpha.astype(np.int16) * 2 - 255), 0, 255))
        # The repository adapter decodes protection PNGs into bool arrays.
        # Hash that canonical representation rather than the transport's
        # uint8 {0,255} pixels, otherwise a valid response is rejected as
        # stale before it reaches the domain core.
        proposal_hash = hashlib.sha256(alpha.tobytes() + (protection > 0).tobytes() + uncertainty.tobytes()).hexdigest()
        return {
            "alpha_png_base64": _encode_mask(alpha),
            "protection_png_base64": _encode_mask(protection),
            "uncertainty_png_base64": _encode_mask(uncertainty),
            "model": "BiRefNet HR-matting" if self.kind == "birefnet" else "BEN2",
            "version": self.model_version,
            "license": self.model_license,
            "weights_sha256": self.weights_sha256,
            "proposal_sha256": proposal_hash,
            "inference_seconds": elapsed,
            "mask_tuning": _dynamic_tuning(source, alpha, source_sha256),
            "visual_quality": _visual_preflight(alpha, source_sha256),
        }


def build_app(model: ProposalModel) -> FastAPI:
    app = FastAPI(title=f"{model.kind} proposal adapter", version=model.model_version)

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "model_kind": model.kind,
            "model_version": model.model_version,
            "weights_sha256": model.weights_sha256,
        }

    @app.post("/v1/proposal")
    async def proposal(request: Request) -> dict[str, Any]:
        payload = await request.body()
        source = _decode_source(payload)
        return model.response(source)

    return app


model = ProposalModel()
app = build_app(model)
