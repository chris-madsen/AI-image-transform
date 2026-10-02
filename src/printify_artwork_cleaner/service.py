from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from .adapters.filesystem import FileJobStore, sha256_bytes
from .adapters.photopea import PhotopeaLiveApiAdapter
from .application import process_image_bytes
from .domain.models import Err, JobStatus, freeze_policy


LOGGER = logging.getLogger("printify_artwork_cleaner")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

JOBS_TOTAL = Counter("artwork_jobs_total", "Submitted artwork jobs", ("status",))
JOB_DURATION = Histogram("artwork_job_duration_seconds", "Artwork processing duration")
QUEUE_DEPTH = Gauge("artwork_job_queue_depth", "Jobs currently being processed")
VALIDATION_TOTAL = Counter("artwork_validation_total", "Validation decisions", ("decision",))
ARTIFACTS_TOTAL = Counter("artwork_artifacts_total", "Written artifacts", ("media_type",))
HTTP_TOTAL = Counter("artwork_http_requests_total", "HTTP requests", ("method", "route", "status"))


def _event(event_type: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event_type": event_type, **fields}, ensure_ascii=False, sort_keys=True))


class ServiceRuntime:
    def __init__(self, root: Path, token: str | None = None, psd_exporter=None) -> None:
        self.store = FileJobStore(root)
        self.token = token
        photopea_url = os.getenv("PHOTOPEA_LIVE_API_URL")
        self.psd_exporter = psd_exporter or (PhotopeaLiveApiAdapter(photopea_url, os.getenv("PHOTOPEA_LIVE_API_TOKEN")) if photopea_url else None)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="artwork-job")

    def submit(self, source: bytes, policy_payload: dict[str, Any], manifest: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
        source_hash = sha256_bytes(source)
        if idempotency_key:
            existing = self.store.find_idempotent(idempotency_key, source_hash)
            if existing:
                return self.status(existing.job_id)
        job_id = uuid4().hex
        record = self.store.create(job_id, source_hash, idempotency_key, {"manifest": manifest, "policy": policy_payload})
        job_dir = self.store.job_dir(job_id)
        (job_dir / "source.bin").write_bytes(source)
        (job_dir / "policy.json").write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.executor.submit(self._run, job_id, source, policy_payload)
        JOBS_TOTAL.labels(status="accepted").inc()
        _event("JobAccepted", job_id=job_id, correlation_id=manifest.get("correlation_id"))
        return self.status(record.job_id)

    def _run(self, job_id: str, source: bytes, payload: dict[str, Any]) -> None:
        started = time.perf_counter()
        QUEUE_DEPTH.inc()
        self.store.update(job_id, status=JobStatus.RUNNING.value, progress=10)
        _event("JobStarted", job_id=job_id)
        try:
            parsed = freeze_policy(payload)
            if isinstance(parsed, Err):
                self.store.update(job_id, status=JobStatus.FAILED.value, progress=100, error={"code": parsed.error.code, "path": parsed.error.path, "message": parsed.error.message})
                JOBS_TOTAL.labels(status="failed").inc()
                return
            output_dir = self.store.job_dir(job_id) / "artifacts"
            report = process_image_bytes(source, parsed.value, output_dir, psd_exporter=self.psd_exporter)
            self.store.update(job_id, status=report.status.value, progress=100, payload={"report": report.as_dict(), "policy": payload})
            JOBS_TOTAL.labels(status=report.status.value).inc()
            VALIDATION_TOTAL.labels(decision=report.status.value).inc()
            for artifact in report.artifacts:
                ARTIFACTS_TOTAL.labels(media_type=artifact.media_type).inc()
            _event("ValidationCompleted", job_id=job_id, status=report.status.value)
        except Exception as exc:  # imperative shell boundary: unexpected bugs become explicit failed jobs
            self.store.update(job_id, status=JobStatus.FAILED.value, progress=100, error={"code": "processing_failed", "path": "job", "message": str(exc)})
            JOBS_TOTAL.labels(status="failed").inc()
            _event("JobFailed", job_id=job_id, error_type=type(exc).__name__)
        finally:
            QUEUE_DEPTH.dec()
            JOB_DURATION.observe(time.perf_counter() - started)

    def status(self, job_id: str) -> dict[str, Any]:
        record = self.store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "unknown job"})
        result = {
            "job_id": record.job_id,
            "status": record.status,
            "progress": record.progress,
            "source_hash": record.source_hash,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "error": record.error,
        }
        if "report" in record.payload:
            result["report"] = record.payload["report"]
        return result

    def artifacts(self, job_id: str) -> list[dict[str, Any]]:
        record = self.store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "unknown job"})
        directory = self.store.job_dir(job_id) / "artifacts"
        return [
            {"name": path.name, "size_bytes": path.stat().st_size, "download_url": f"/v1/artifacts/{job_id}/{path.name}"}
            for path in sorted(directory.iterdir()) if path.is_file()
        ] if directory.exists() else []


def create_app(root: Path | None = None, token: str | None = None, psd_exporter=None) -> FastAPI:
    runtime = ServiceRuntime(root or Path(os.getenv("ARTIFACT_ROOT", "artifacts/service")), token if token is not None else os.getenv("ARTWORK_SERVICE_TOKEN"), psd_exporter=psd_exporter)
    app = FastAPI(title="Printify Artwork Cleaner", version="0.1.0")
    app.state.runtime = runtime

    def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        if runtime.token and authorization != f"Bearer {runtime.token}":
            raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "invalid bearer token"})

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/jobs", status_code=202, dependencies=[Depends(require_auth)])
    async def create_job(
        source: Annotated[UploadFile, File(...)],
        policy_json: Annotated[str, Form(...)],
        manifest_json: Annotated[str, Form()] = "{}",
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        raw = await source.read()
        max_bytes = int(os.getenv("MAX_SOURCE_BYTES", str(100 * 1024 * 1024)))
        if len(raw) > max_bytes:
            raise HTTPException(status_code=413, detail={"code": "source_too_large", "message": "source exceeds configured limit"})
        try:
            policy = json.loads(policy_json)
            manifest = json.loads(manifest_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_json", "message": str(exc)}) from exc
        frozen = freeze_policy(policy)
        if isinstance(frozen, Err):
            raise HTTPException(status_code=422, detail={"code": frozen.error.code, "path": frozen.error.path, "message": frozen.error.message})
        result = runtime.submit(raw, policy, manifest, idempotency_key)
        return JSONResponse({"job_id": result["job_id"], "status": result["status"], "poll_url": f"/v1/jobs/{result['job_id']}"}, status_code=202)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_auth)])
    def get_job(job_id: str) -> dict[str, Any]:
        return runtime.status(job_id)

    @app.get("/v1/jobs/{job_id}/artifacts", dependencies=[Depends(require_auth)])
    def list_artifacts(job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "artifacts": runtime.artifacts(job_id)}

    @app.get("/v1/artifacts/{job_id}/{name}", dependencies=[Depends(require_auth)])
    def download_artifact(job_id: str, name: str) -> FileResponse:
        if Path(name).name != name or name in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail={"code": "invalid_artifact_name", "message": "invalid artifact name"})
        path = runtime.store.job_dir(job_id) / "artifacts" / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "artifact_not_found", "message": "unknown artifact"})
        return FileResponse(path)

    return app


app = create_app()
