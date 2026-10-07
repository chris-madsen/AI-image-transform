"""Serve a fail-closed multimodal Photopea checkpoint reviewer.

The reviewer is intentionally a deployment adapter, not part of the image
processing core.  It sends the exact checkpoint PNG bytes to an
OpenAI-compatible vision endpoint and returns only a typed accept/reject
decision.  It cannot create Photopea scripts or silently invent a raster
correction.  A rejected checkpoint therefore remains ``review_required``
unless a separate trusted provider supplies a hash-bound correction carrier.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise HTTPException(status_code=422, detail=f"invalid {field}")
    return value.lower()


def _data_url(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _review_prompt() -> str:
    return """You are a strict print-artwork quality reviewer.

Inspect the supplied Photopea checkpoint images as one result. The transparent
artwork and grayscale mask must be judged together with the black, navy and
blue-jean previews. Compare the checkpoint to the source pixels mentally: RGB
must not have been regenerated or repainted.

Accept only when all of these are true:
- the main subject is intact, including both ears, eyes, whiskers and thin
  intentional details;
- intentional foliage, leaves, splashes or typography are not accidentally
  removed;
- there is no rectangular frame, broad translucent veil, colored halo or
  visible background contamination on dark garments;
- the outer transition is intentional and print-safe, not a continuous glow;
- the result is aesthetically coherent as a printable composition.

Return JSON only with this exact shape:
{"accepted":true|false,"confidence":0.0,"notes":["short reason"]}

Set accepted=false whenever any required detail is uncertain. Do not suggest
coordinates, polygons or scripts. This endpoint has no correction-mask
generator, so rejection is safer than guessing."""


class VisionReviewer:
    def __init__(self) -> None:
        self.endpoint = os.getenv("VISION_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions").rstrip("/")
        self.api_key = _required("VISION_LLM_API_KEY")
        self.model = _required("VISION_LLM_MODEL")
        self.timeout = float(os.getenv("VISION_LLM_TIMEOUT", "120"))

    def review(self, checkpoint: dict[str, Any], images: dict[str, bytes]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": _review_prompt()}]
        for label, payload in sorted(images.items()):
            content.append({"type": "text", "text": f"Checkpoint image: {label}"})
            content.append({"type": "image_url", "image_url": {"url": _data_url(payload), "detail": "high"}})
        request_payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }
        request = Request(
            self.endpoint,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="vision model unavailable") from exc
        try:
            text = body["choices"][0]["message"]["content"]
            decision = json.loads(text)
            accepted = decision["accepted"]
            confidence = float(decision["confidence"])
            notes = tuple(str(item) for item in decision.get("notes", ()))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="vision model returned invalid review JSON") from exc
        if not isinstance(accepted, bool) or not 0 <= confidence <= 1 or not notes:
            raise HTTPException(status_code=502, detail="vision model returned unsafe review evidence")
        # A model may only accept with high confidence. Rejection is always
        # safe and remains review_required in the processing service.
        return {
            "accepted": accepted and confidence >= 0.8,
            "confidence": confidence,
            "notes": list(notes),
            "source_sha256": _sha256(checkpoint.get("source_sha256"), "source_sha256"),
            "checkpoint_sha256": _sha256(checkpoint.get("checkpoint_sha256"), "checkpoint_sha256"),
        }


reviewer = VisionReviewer()
app = FastAPI(title="Photopea multimodal checkpoint reviewer")


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "model": reviewer.model}


@app.post("/v1/review")
async def review(checkpoint: str = Form(...), artwork: UploadFile = File(...), mask: UploadFile = File(...), preview_black: UploadFile = File(...), preview_navy: UploadFile = File(...), preview_blue_jean: UploadFile = File(...)) -> dict[str, Any]:
    try:
        checkpoint_payload = json.loads(checkpoint)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="checkpoint must be JSON") from exc
    if not isinstance(checkpoint_payload, dict):
        raise HTTPException(status_code=422, detail="checkpoint must be an object")
    uploads = {item.filename or "unknown": item for item in (artwork, mask, preview_black, preview_navy, preview_blue_jean)}
    images = {name: await item.read() for name, item in uploads.items()}
    if any(not value for value in images.values()):
        raise HTTPException(status_code=422, detail="checkpoint images must not be empty")
    return reviewer.review(checkpoint_payload, images)
