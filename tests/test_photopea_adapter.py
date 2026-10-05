from __future__ import annotations

import hashlib
import io
import json

import numpy as np
import pytest
from PIL import Image

from printify_artwork_cleaner.adapters.photopea import PhotopeaLiveApiUnavailable, PhotopeaLiveApiAdapter, _mask_png_bytes


def _revision(mask: np.ndarray) -> dict[str, object]:
    return {
        "revision_id": "vision-r1",
        "parent_revision_id": None,
        "source_sha256": "a" * 64,
        "checkpoint_sha256": "b" * 64,
        "base_mask_sha256": "c" * 64,
        "result_mask_sha256": hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
        "operation": "replace_mask",
        "confidence": 0.9,
    }


def _evidence(mask_hash: str) -> str:
    return json.dumps({
        "source_sha256": "a" * 64,
        "result_mask_sha256": mask_hash,
        "checkpoint_sha256": "b" * 64,
        "artwork_sha256": "f" * 64,
        "preview_sha256": ["1" * 64, "2" * 64, "3" * 64],
        "reopened": True,
        "required_layers": ["SOURCE BACKUP", "RESTORED", "WITH GAPS", "WORKING MASK"],
    })


def test_mask_carrier_preserves_partial_values_as_opaque_grayscale() -> None:
    mask = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    with Image.open(io.BytesIO(_mask_png_bytes(mask))) as image:
        carrier = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    assert carrier[..., 0].tolist() == mask.tolist()
    assert np.array_equal(carrier[..., 0], carrier[..., 1])
    assert np.array_equal(carrier[..., 1], carrier[..., 2])
    assert np.all(carrier[..., 3] == 255)


def test_photopea_exporter_posts_one_source_and_one_raster_mask(monkeypatch) -> None:
    calls = {}
    mask_hash = hashlib.sha256(np.full((4, 4), 255, dtype=np.uint8).tobytes()).hexdigest()

    class Response:
        headers = {"X-Photopea-Roundtrip": "verified", "X-Photopea-Evidence": _evidence(mask_hash)}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"8BPS" + b"photopea-result"

    def fake_urlopen(request, timeout):
        calls["url"] = request.full_url
        calls["body"] = request.data
        calls["timeout"] = timeout
        return Response()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", fake_urlopen)
    source = np.zeros((4, 4, 4), dtype=np.uint8)
    mask = np.full((4, 4), 255, dtype=np.uint8)
    adapter = PhotopeaLiveApiAdapter("http://bridge", token="secret")
    result = adapter.export(source, source, mask, mask_revision=_revision(mask))
    assert result.startswith(b"8BPS")
    assert calls["url"] == "http://bridge/v1/photopea/export"
    assert b'name="source"' in calls["body"]
    assert b'name="mask"' in calls["body"]
    assert b'mask_revision' in calls["body"]
    assert b'variant_artistic' not in calls["body"]
    assert b'subject_polygons' not in calls["body"]
    assert adapter.round_trip_verified is True
    assert adapter.evidence is not None and adapter.evidence.reopened is True


def test_photopea_exporter_rejects_non_psd(monkeypatch) -> None:
    class Response:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"not-psd"

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", lambda *args, **kwargs: Response())
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=_revision(mask))


def test_photopea_session_rejects_stale_mask_hash(monkeypatch) -> None:
    adapter = PhotopeaLiveApiAdapter("http://bridge")
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    stale = _revision(mask)
    stale["result_mask_sha256"] = "0" * 64
    with pytest.raises(PhotopeaLiveApiUnavailable, match="does not match"):
        adapter.export(source, source, mask, mask_revision=stale)


def test_photopea_exporter_rejects_verified_header_without_pixel_evidence(monkeypatch) -> None:
    class Response:
        headers = {"X-Photopea-Roundtrip": "verified"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"8BPS" + b"payload"

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", lambda *args, **kwargs: Response())
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    mask = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable, match="pixel round-trip evidence"):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, mask, mask_revision=_revision(mask))
