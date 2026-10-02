from __future__ import annotations

import io
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from printify_artwork_cleaner.service import create_app


class FakePhotopeaExporter:
    def export(self, source, artwork, mask) -> bytes:
        return b"8BPS" + b"fake-photopea-psd"


def _source() -> bytes:
    image = Image.new("RGBA", (24, 24), (120, 140, 160, 255))
    for x in range(6, 18):
        for y in range(6, 18):
            image.putpixel((x, y), (220, 30, 30, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _wait_for_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"passed", "review_required", "refused", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_async_job_contract_and_artifacts(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, psd_exporter=FakePhotopeaExporter()))
    response = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={"policy_json": json.dumps({"requested_variants": ["conservative"]}), "manifest_json": "{}"},
        headers={"Idempotency-Key": "test-1"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    terminal = _wait_for_terminal(client, job_id)
    assert terminal["status"] in {"passed", "review_required", "refused"}
    artifacts = client.get(f"/v1/jobs/{job_id}/artifacts").json()["artifacts"]
    names = {item["name"] for item in artifacts}
    assert "artwork_editable.psd" in names
    assert "report.json" in names
    downloaded = client.get(f"/v1/artifacts/{job_id}/report.json")
    assert downloaded.status_code == 200

    retry = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={"policy_json": "{}", "manifest_json": "{}"},
        headers={"Idempotency-Key": "test-1"},
    )
    assert retry.status_code == 202
    assert retry.json()["job_id"] == job_id


def test_auth_and_invalid_policy(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, token="secret", psd_exporter=FakePhotopeaExporter()))
    unauthorized = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={"policy_json": "{}"},
    )
    assert unauthorized.status_code == 401
    invalid = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={"policy_json": json.dumps({"edge_strategy": "nope"})},
        headers={"Authorization": "Bearer secret"},
    )
    assert invalid.status_code == 422
