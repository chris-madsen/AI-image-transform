from __future__ import annotations

import hashlib
import io
import json

import numpy as np
import pytest
from PIL import Image

from printify_artwork_cleaner.adapters.photopea import PhotopeaLiveApiUnavailable, PhotopeaLiveApiAdapter, _mask_png_bytes, review_acceptance_token


def _revision(mask: np.ndarray) -> dict[str, object]:
    return {
        "revision_id": "vision-r1",
        "parent_revision_id": None,
        "source_sha256": "a" * 64,
        "checkpoint_sha256": "",
        "base_mask_sha256": "c" * 64,
        "result_mask_sha256": hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
        "operation": "replace_mask",
        "confidence": 0.9,
    }


def test_review_acceptance_token_is_bound_to_current_checkpoint(monkeypatch) -> None:
    monkeypatch.setenv("PHOTOPEA_REVIEW_SECRET", "test-secret")
    revision = _revision(np.zeros((2, 2), dtype=np.uint8))
    revision["checkpoint_sha256"] = "b" * 64
    token = review_acceptance_token(revision)
    assert len(token) == 64
    changed = dict(revision, checkpoint_sha256="c" * 64)
    assert review_acceptance_token(changed) != token


def test_mask_carrier_preserves_partial_values_as_opaque_grayscale() -> None:
    mask = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    with Image.open(io.BytesIO(_mask_png_bytes(mask))) as image:
        carrier = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    assert carrier[..., 0].tolist() == mask.tolist()
    assert np.array_equal(carrier[..., 0], carrier[..., 1])
    assert np.array_equal(carrier[..., 1], carrier[..., 2])
    assert np.all(carrier[..., 3] == 255)


def test_photopea_exporter_rejects_unreviewed_one_shot_path() -> None:
    source = np.zeros((4, 4, 4), dtype=np.uint8)
    mask = np.full((4, 4), 255, dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable, match="one-shot Photopea export is disabled"):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=_revision(mask))


def test_photopea_exporter_rejects_non_psd(monkeypatch) -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable, match="one-shot Photopea export is disabled"):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=_revision(mask))


def test_photopea_session_rejects_stale_mask_hash(monkeypatch) -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    stale = _revision(mask)
    stale["result_mask_sha256"] = "0" * 64
    with pytest.raises(PhotopeaLiveApiUnavailable, match="one-shot Photopea export is disabled"):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=stale)


def test_photopea_exporter_rejects_verified_header_without_pixel_evidence(monkeypatch) -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable, match="one-shot Photopea export is disabled"):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=_revision(mask))
