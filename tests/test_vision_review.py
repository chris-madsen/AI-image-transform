from __future__ import annotations

import base64
import hashlib
import json

import pytest

from printify_artwork_cleaner.adapters.vision_review import HttpVisionReviewer, VisionReviewUnavailable
from printify_artwork_cleaner.domain.models import PhotopeaCheckpoint


def _checkpoint() -> PhotopeaCheckpoint:
    return PhotopeaCheckpoint("r1", "r1", "a" * 64, "b" * 64, "c" * 64, "d" * 64)


def test_http_reviewer_sends_checkpoint_artifacts_and_parses_acceptance(monkeypatch) -> None:
    checkpoint = _checkpoint()
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"accepted": True, "source_sha256": checkpoint.source_sha256, "checkpoint_sha256": checkpoint.checkpoint_sha256}).encode()

    def fake_urlopen(request, **_kwargs):
        observed["body"] = request.data
        observed["content_type"] = request.headers["Content-type"]
        return Response()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.vision_review.urlopen", fake_urlopen)
    decision = HttpVisionReviewer("http://vision.test/review")(checkpoint, {"artwork": b"art", "mask": b"mask"})
    assert decision.accepted is True
    assert b'name="artwork"' in observed["body"]
    assert b'name="mask"' in observed["body"]


def test_http_reviewer_rejects_stale_correction(monkeypatch) -> None:
    checkpoint = _checkpoint()
    correction = base64.b64encode(b"mask").decode()
    payload = {
        "accepted": False,
        "source_sha256": checkpoint.source_sha256,
        "checkpoint_sha256": checkpoint.checkpoint_sha256,
        "correction_mask_png_base64": correction,
        "revision": {
            "revision_id": "r2",
            "parent_revision_id": "r1",
            "source_sha256": "e" * 64,
            "checkpoint_sha256": checkpoint.checkpoint_sha256,
            "base_mask_sha256": "c" * 64,
            "result_mask_sha256": hashlib.sha256(b"mask").hexdigest(),
            "confidence": 0.9,
        },
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.vision_review.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(VisionReviewUnavailable, match="another checkpoint"):
        HttpVisionReviewer("http://vision.test/review")(checkpoint, {"artwork": b"art", "mask": b"mask"})
