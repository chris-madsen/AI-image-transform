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
    result = PhotopeaLiveApiAdapter("http://bridge", token="secret").export(source, source, source[..., 3])
    assert result.startswith(b"8BPS")
    assert calls["url"] == "http://bridge/v1/photopea/export"
    assert b"SOURCE BACKUP" in calls["body"]
    assert b"WORKING ART" in calls["body"]
    assert b"WORKING MASK" in calls["body"]
    assert b"BLUE JEAN" in calls["body"]
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
