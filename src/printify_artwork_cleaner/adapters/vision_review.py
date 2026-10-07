from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import asdict
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..domain.models import MaskReviewDecision, PhotopeaCheckpoint, RasterMaskRevision


class VisionReviewUnavailable(RuntimeError):
    """The configured checkpoint reviewer did not return typed evidence."""


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise VisionReviewUnavailable(f"review response has invalid {field}")
    return value.lower()


class HttpVisionReviewer:
    """HTTP adapter for an external multimodal checkpoint reviewer.

    The reviewer receives the actual checkpoint bytes, not hashes alone. It may
    accept the checkpoint or return one grayscale correction carrier together
    with a hash-bound `RasterMaskRevision`; it cannot return Photopea scripts.
    """

    def __init__(self, endpoint: str, *, token: str | None = None, timeout: float = 120.0) -> None:
        if not endpoint:
            raise ValueError("vision review endpoint is required")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout

    def __call__(self, checkpoint: PhotopeaCheckpoint, artifacts: Mapping[str, bytes]) -> MaskReviewDecision:
        boundary = "----artwork-vision-review-" + hashlib.sha256(checkpoint.checkpoint_sha256.encode()).hexdigest()[:24]
        fields = {"checkpoint": json.dumps(asdict(checkpoint), separators=(",", ":"))}
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
        for label, content in sorted(artifacts.items()):
            parts.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{label}"; filename="{label}.png"\r\n'.encode(),
                b"Content-Type: image/png\r\n\r\n",
                content,
                b"\r\n",
            ])
        parts.append(f"--{boundary}--\r\n".encode())
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urlopen(Request(self.endpoint, data=b"".join(parts), headers=headers, method="POST"), timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VisionReviewUnavailable(f"vision review endpoint unavailable: {exc}") from exc
        if not isinstance(payload, dict):
            raise VisionReviewUnavailable("vision review response must be an object")
        source_sha256 = _sha256(payload.get("source_sha256"), "source_sha256")
        checkpoint_sha256 = _sha256(payload.get("checkpoint_sha256"), "checkpoint_sha256")
        if source_sha256 != checkpoint.source_sha256 or checkpoint_sha256 != checkpoint.checkpoint_sha256:
            raise VisionReviewUnavailable("vision review response is bound to another checkpoint")
        accepted = payload.get("accepted")
        if not isinstance(accepted, bool):
            raise VisionReviewUnavailable("vision review response requires boolean accepted")
        revision_payload = payload.get("revision")
        correction_payload = payload.get("correction_mask_png_base64")
        revision = None
        correction = None
        if revision_payload is not None:
            if not isinstance(revision_payload, dict) or not isinstance(correction_payload, str):
                raise VisionReviewUnavailable("vision correction requires revision metadata and base64 mask")
            try:
                revision = RasterMaskRevision(
                    revision_id=str(revision_payload["revision_id"]),
                    parent_revision_id=revision_payload.get("parent_revision_id"),
                    source_sha256=_sha256(revision_payload["source_sha256"], "revision.source_sha256"),
                    checkpoint_sha256=_sha256(revision_payload["checkpoint_sha256"], "revision.checkpoint_sha256"),
                    base_mask_sha256=_sha256(revision_payload["base_mask_sha256"], "revision.base_mask_sha256"),
                    result_mask_sha256=_sha256(revision_payload["result_mask_sha256"], "revision.result_mask_sha256"),
                    operation=str(revision_payload.get("operation", "replace_mask")),
                    confidence=float(revision_payload.get("confidence", 0.0)),
                )
                correction = base64.b64decode(correction_payload, validate=True)
            except (KeyError, TypeError, ValueError) as exc:
                raise VisionReviewUnavailable("vision correction is malformed") from exc
            if revision.source_sha256 != source_sha256 or revision.checkpoint_sha256 != checkpoint_sha256:
                raise VisionReviewUnavailable("vision correction is bound to another checkpoint")
            if not revision.revision_id or not 0 <= revision.confidence <= 1 or not correction:
                raise VisionReviewUnavailable("vision correction has invalid confidence or empty mask")
        return MaskReviewDecision(accepted, source_sha256, checkpoint_sha256, revision, correction)


def configured_vision_reviewer() -> HttpVisionReviewer | None:
    endpoint = os.getenv("VISION_REVIEW_ENDPOINT")
    if not endpoint:
        return None
    try:
        return HttpVisionReviewer(endpoint, token=os.getenv("VISION_REVIEW_TOKEN"), timeout=float(os.getenv("VISION_REVIEW_TIMEOUT", "120")))
    except (TypeError, ValueError):
        return None
