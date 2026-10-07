"""Serve pinned SAM 2.1 semantic-protection proposals over HTTP.

Deployment-only adapter. SAM automatic masks are used as a protection hint for
the deterministic external-edge remover; they are never promoted to artwork
alpha. The process refuses to start when the checkpoint hash or release
metadata is missing or incorrect.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from PIL import Image

from printify_artwork_cleaner.domain.image_math import canonical_rgba_png_bytes


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


class SAM2ProtectionModel:
    def __init__(self) -> None:
        self.model_version = _required("SAM2_MODEL_VERSION")
        self.model_license = _required("SAM2_MODEL_LICENSE")
        self.weights_path = Path(_required("SAM2_MODEL_CHECKPOINT"))
        self.weights_sha256 = _required("SAM2_WEIGHTS_SHA256").lower()
        if len(self.weights_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.weights_sha256):
            raise RuntimeError("SAM2_WEIGHTS_SHA256 must be a lowercase SHA-256")
        actual_hash = _sha256(self.weights_path)
        if actual_hash != self.weights_sha256:
            raise RuntimeError(f"weights hash mismatch: expected {self.weights_sha256}, got {actual_hash}")
        self.config = _required("SAM2_MODEL_CONFIG")
        self.device = os.getenv("SAM2_MODEL_DEVICE", "cpu")
        self.min_iou = float(os.getenv("SAM2_MIN_PREDICTED_IOU", "0.70"))
        self.min_stability = float(os.getenv("SAM2_MIN_STABILITY_SCORE", "0.70"))
        self.min_area = int(os.getenv("SAM2_MIN_MASK_AREA", "64"))
        self.max_area_fraction = float(os.getenv("SAM2_MAX_MASK_AREA_FRACTION", "0.80"))
        self.lock = threading.Lock()
        self.generator = self._load()

    def _load(self) -> Any:
        try:
            import torch
            from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
            from sam2.build_sam import build_sam2
        except ImportError as exc:
            raise RuntimeError("SAM2 runtime is not installed in this deployment environment") from exc
        model = build_sam2(self.config, str(self.weights_path), device=self.device)
        return SAM2AutomaticMaskGenerator(model)

    @staticmethod
    def _touches_border(mask: np.ndarray) -> bool:
        return bool(np.any(mask[0]) or np.any(mask[-1]) or np.any(mask[:, 0]) or np.any(mask[:, -1]))

    def predict(self, source: np.ndarray) -> np.ndarray:
        rgb = np.asarray(source[..., :3], dtype=np.uint8)
        with self.lock:
            candidates = self.generator.generate(rgb)
        protection = np.zeros(source.shape[:2], dtype=bool)
        max_area = int(source.shape[0] * source.shape[1] * self.max_area_fraction)
        for candidate in candidates:
            mask = np.asarray(candidate.get("segmentation"), dtype=bool)
            area = int(np.count_nonzero(mask))
            if area < self.min_area or area > max_area or self._touches_border(mask):
                continue
            if float(candidate.get("predicted_iou", 0.0)) < self.min_iou:
                continue
            if float(candidate.get("stability_score", 0.0)) < self.min_stability:
                continue
            protection |= mask
        return np.where(protection, 255, 0).astype(np.uint8)

    def response(self, source: np.ndarray) -> dict[str, Any]:
        source_hash = hashlib.sha256(canonical_rgba_png_bytes(source)).hexdigest()
        protection = self.predict(source)
        uncertainty = np.where(protection > 0, 0, 255).astype(np.uint8)
        proposal_hash = hashlib.sha256((protection > 0).tobytes() + uncertainty.tobytes()).hexdigest()
        return {
            "protection_png_base64": _encode_mask(protection),
            "uncertainty_png_base64": _encode_mask(uncertainty),
            "model": "SAM 2.1",
            "version": self.model_version,
            "license": self.model_license,
            "weights_sha256": self.weights_sha256,
            "source_sha256": source_hash,
            "proposal_sha256": proposal_hash,
            "protection_policy": {
                "border_touching_masks": "excluded",
                "matting_alpha": "never_emitted",
            },
        }


model = SAM2ProtectionModel()
app = FastAPI(title="SAM 2.1 protection adapter", version=model.model_version)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "model": "SAM 2.1", "version": model.model_version, "weights_sha256": model.weights_sha256}


@app.post("/v1/protection")
async def protection(request: Request) -> dict[str, Any]:
    return model.response(_decode_source(await request.body()))
