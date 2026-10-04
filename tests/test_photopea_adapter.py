from __future__ import annotations

import numpy as np
import pytest

from printify_artwork_cleaner.adapters.photopea import PhotopeaLiveApiUnavailable, PhotopeaLiveApiAdapter


def test_photopea_exporter_posts_candidates_and_accepts_psd(monkeypatch) -> None:
    calls = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"8BPS" + b"photopea-result"

    def fake_urlopen(request, timeout):
        calls["url"] = request.full_url
        calls["content_type"] = request.headers["Content-type"]
        calls["body"] = request.data
        calls["timeout"] = timeout
        return Response()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", fake_urlopen)
    source = np.zeros((4, 4, 4), dtype=np.uint8)
    result = PhotopeaLiveApiAdapter("http://bridge", token="secret").export(
        source,
        source,
        source[..., 3],
        variants={"artistic": source, "conservative": source},
    )
    assert result.startswith(b"8BPS")
    assert calls["url"] == "http://bridge/v1/photopea/export"
    assert b"SOURCE BACKUP" in calls["body"]
    assert b"RESTORED" in calls["body"]
    assert b"WITH GAPS" in calls["body"]
    assert b"WORKING MASK" in calls["body"]
    assert b"BLUE JEAN" in calls["body"]
    assert b"variant_artistic" in calls["body"]
    assert b"mask_conservative" in calls["body"]
    assert b"request_json" in calls["body"]


def test_photopea_exporter_rejects_non_psd(monkeypatch) -> None:
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"not-psd"

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", lambda *args, **kwargs: Response())
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    with pytest.raises(PhotopeaLiveApiUnavailable):
        PhotopeaLiveApiAdapter("http://bridge").export(source, source, source[..., 3])


def test_photopea_session_sends_only_source_and_typed_plan(monkeypatch) -> None:
    calls = {}

    class Response:
        headers = {"X-Photopea-Roundtrip": "verified"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"8BPS" + b"session"

    def fake_urlopen(request, timeout):
        calls["body"] = request.data
        return Response()

    monkeypatch.setattr("printify_artwork_cleaner.adapters.photopea.urlopen", fake_urlopen)
    source = np.zeros((4, 4, 4), dtype=np.uint8)
    plan = {
        "revision_id": "vision-r1",
        "subject_polygons": [[[0, 0], [1, 0], [1, 1]]],
        "remove_polygons": [],
        "protect_polygons": [],
        "feather_px": 1,
        "confidence": 0.9,
    }
    adapter = PhotopeaLiveApiAdapter("http://bridge")
    result = adapter.export(source, source, source[..., 3], mask_plan=plan)
    assert result.startswith(b"8BPS")
    assert b'name="source"' in calls["body"]
    assert b'name="mask_plan"' in calls["body"]
    assert b'variant_artistic' not in calls["body"]
    assert adapter.round_trip_verified is True
