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
    assert terminal["status"] == "review_required"
    assert "model_proposal" in terminal["report"]["validation"]["review_regions"]
    artifacts = client.get(f"/v1/jobs/{job_id}/artifacts").json()["artifacts"]
    names = {item["name"] for item in artifacts}
    assert "artwork_editable.psd" in names
    assert "report.json" in names
    assert terminal["report"]["psd_export_status"] == "unverified"
    assert terminal["report"]["stage_status"]["psd_validation_status"] == "unverified_payload"
    assert terminal["report"]["artifact_set"]["source"] == "photopea_export"
    assert terminal["report"]["artifact_set"]["authoritative_artifacts"] == ["artwork_editable.psd"]
    report_entries = {item["name"]: item for item in terminal["report"]["artifacts"]}
    assert report_entries["artwork_editable.psd"]["authoritative"] is True
    assert report_entries["artwork_conservative.png"]["authoritative"] is False
    assert report_entries["artwork_conservative.png"]["role"] == "proposal"
    assert report_entries["report.json"]["role"] == "proposal"
    assert {item["name"]: item["authoritative"] for item in artifacts}["artwork_editable.psd"] is True
    downloaded = client.get(f"/v1/artifacts/{job_id}/report.json")
    assert downloaded.status_code == 200

    retry = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={"policy_json": "{}", "manifest_json": "{}"},
        headers={"Idempotency-Key": "test-1"},
    )
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "idempotency_conflict"


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


def test_public_job_rejects_authoritative_photopea_mask(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, psd_exporter=FakePhotopeaExporter()))
    response = client.post(
        "/v1/jobs",
        files={
            "source": ("art.png", _source(), "image/png"),
            "photopea_mask": ("mask.png", _source(), "image/png"),
        },
        data={"policy_json": "{}", "manifest_json": "{}"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "forbidden_final_mask_input"


def test_public_job_rejects_client_visual_quality_evidence(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, psd_exporter=FakePhotopeaExporter()))
    response = client.post(
        "/v1/jobs",
        files={"source": ("art.png", _source(), "image/png")},
        data={
            "policy_json": json.dumps({"visual_quality": {"overall_score": 1.0}}),
            "manifest_json": "{}",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "forbidden"


def test_artifact_paths_reject_traversal(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path, psd_exporter=FakePhotopeaExporter()))
    assert client.get("/v1/jobs/../secrets").status_code in {400, 404}
    assert client.get("/v1/artifacts/../../secret.txt").status_code in {400, 404}
