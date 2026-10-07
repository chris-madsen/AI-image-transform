from __future__ import annotations

import json
import logging
import os
import time
import hashlib
import re
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from PIL import Image
import io
import numpy as np

from .adapters.filesystem import FileJobStore, sha256_bytes
from .adapters.model_proposals import ModelProposalUnavailable, configured_consensus_provider
from .adapters.photopea import PhotopeaLiveApiAdapter, PhotopeaLiveApiUnavailable, PhotopeaSessionClient
from .adapters.vision_review import configured_vision_reviewer
from .application import process_image_bytes
from .domain.image_math import canonical_png_sha256
from .domain.models import Err, JobStatus, MaskReviewDecision, PhotopeaCheckpoint, RasterMaskRevision, ResolvedMaskBundle, freeze_policy


LOGGER = logging.getLogger("printify_artwork_cleaner")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

JOBS_TOTAL = Counter("artwork_jobs_total", "Submitted artwork jobs", ("status",))
JOB_DURATION = Histogram("artwork_job_duration_seconds", "Artwork processing duration")
QUEUE_DEPTH = Gauge("artwork_job_queue_depth", "Jobs currently being processed")
VALIDATION_TOTAL = Counter("artwork_validation_total", "Validation decisions", ("decision",))
ARTIFACTS_TOTAL = Counter("artwork_artifacts_total", "Written artifacts", ("media_type",))
HTTP_TOTAL = Counter("artwork_http_requests_total", "HTTP requests", ("method", "route", "status"))


def _valid_job_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", value))


def _event(event_type: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event_type": event_type, **fields}, ensure_ascii=False, sort_keys=True))


def _decode_resolved_masks(payloads: dict[str, bytes]) -> ResolvedMaskBundle:
    decoded: dict[str, np.ndarray] = {}
    shapes: set[tuple[int, int]] = set()
    for key, payload in payloads.items():
        with Image.open(io.BytesIO(payload)) as image:
            if key == "protected_reference":
                mask = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            else:
                mask = np.asarray(image.convert("L"), dtype=np.uint8) > 0
        decoded[key] = mask
        shapes.add(mask.shape[:2])
    if len(shapes) > 1:
        raise ValueError("resolved masks must have identical dimensions")
    bundle = ResolvedMaskBundle(
        semantic_protection=decoded.get("semantic_protection"),
        removable_background=decoded.get("removable_background"),
        uncertainty=decoded.get("uncertainty"),
        protected_reference=decoded.get("protected_reference"),
        provenance=("multipart-mask",),
        confidence=1.0,
    )
    return bundle


class ServiceRuntime:
    def __init__(self, root: Path, token: str | None = None, psd_exporter=None, proposal_provider=None, vision_reviewer=None) -> None:
        self.store = FileJobStore(root)
        self.token = token
        photopea_url = os.getenv("PHOTOPEA_LIVE_API_URL")
        photopea_timeout = float(os.getenv("PHOTOPEA_LIVE_API_TIMEOUT", "300"))
        self.psd_exporter = psd_exporter or (PhotopeaLiveApiAdapter(photopea_url, os.getenv("PHOTOPEA_LIVE_API_TOKEN"), timeout=photopea_timeout) if photopea_url else None)
        self.proposal_provider = proposal_provider if proposal_provider is not None else configured_consensus_provider()
        self.vision_reviewer = vision_reviewer if vision_reviewer is not None else configured_vision_reviewer()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="artwork-job")
        self.psd_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photopea-psd")

    def submit(self, source: bytes, policy_payload: dict[str, Any], manifest: dict[str, Any], idempotency_key: str | None, mask_payloads: dict[str, bytes] | None = None) -> dict[str, Any]:
        source_hash = sha256_bytes(source)
        mask_hashes = {name: sha256_bytes(value) for name, value in (mask_payloads or {}).items()}
        fingerprint = hashlib.sha256(json.dumps({"source": source_hash, "policy": policy_payload, "manifest": manifest, "masks": mask_hashes, "pipeline": "2026.10.02.1"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if idempotency_key:
            try:
                existing = self.store.find_idempotent(idempotency_key, fingerprint)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={"code": "idempotency_conflict", "message": str(exc)}) from exc
            if existing:
                return self.status(existing.job_id)
        job_id = uuid4().hex
        record = self.store.create(job_id, source_hash, idempotency_key, {"manifest": manifest, "policy": policy_payload, "_idempotency_fingerprint": fingerprint})
        job_dir = self.store.job_dir(job_id)
        (job_dir / "source.bin").write_bytes(source)
        (job_dir / "policy.json").write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.executor.submit(self._run, job_id, source, policy_payload, mask_payloads or {})
        JOBS_TOTAL.labels(status="accepted").inc()
        _event("JobAccepted", job_id=job_id, correlation_id=manifest.get("correlation_id"))
        return self.status(record.job_id)

    def _run(self, job_id: str, source: bytes, payload: dict[str, Any], mask_payloads: dict[str, bytes]) -> None:
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
            source_rgba = np.asarray(Image.open(io.BytesIO(source)).convert("RGBA"), dtype=np.uint8)
            resolved_masks = _decode_resolved_masks(mask_payloads) if mask_payloads else None
            model_evidence: list[dict[str, Any]] = []
            effective_policy = parsed.value
            if self.proposal_provider is not None:
                proposal = self.proposal_provider.propose(source_rgba, parsed.value)
                if proposal.mask_tuning is None or proposal.visual_quality is None:
                    raise ModelProposalUnavailable("model proposal has no per-artwork tuning and visual-quality decision")
                effective_policy = replace(parsed.value, mask_tuning=proposal.mask_tuning, visual_quality=proposal.visual_quality)
                # Specialized matting models are proposal/evidence providers,
                # not authorities for this product's artistic edge. Their
                # soft alpha and inferred removal masks are precisely what can
                # create a garment halo or erase intentional foliage. The
                # authoritative removal remains the Photopea-style contiguous
                # edge selection in the functional core. Only an explicit
                # semantic protection mask can constrain that selection.
                resolved_masks = ResolvedMaskBundle(
                    semantic_protection=proposal.resolved_masks.semantic_protection,
                    uncertainty=proposal.resolved_masks.uncertainty,
                    provenance=(*proposal.resolved_masks.provenance, "edge-selection-authoritative"),
                    confidence=proposal.resolved_masks.confidence,
                )
                model_evidence = [asdict(item) for item in proposal.evidence]
            # PNG/mask/preview generation is the bounded core job. Photopea
            # is an external, slow adapter and must never block this stage.
            report = process_image_bytes(source, effective_policy, output_dir, psd_exporter=None, resolved_masks=resolved_masks)
            report_payload = report.as_dict()
            if self.proposal_provider is None:
                validation = report_payload["validation"]
                validation["status"] = JobStatus.REVIEW_REQUIRED.value
                validation["warnings"] = list(dict.fromkeys((*validation["warnings"], "specialized_model_proposal_not_configured")))
                validation["review_regions"] = list(dict.fromkeys((*validation["review_regions"], "model_proposal")))
                report_payload["status"] = JobStatus.REVIEW_REQUIRED.value
                report_payload["stage_status"]["overall_status"] = JobStatus.REVIEW_REQUIRED.value
            report_payload["model_evidence"] = model_evidence
            report_payload["psd_export_status"] = "pending" if self.psd_exporter else "not_configured"
            self.store.update(
                job_id,
                status=JobStatus.RUNNING.value if self.psd_exporter else report.status.value,
                progress=85 if self.psd_exporter else 100,
                payload={"report": report_payload, "policy": payload},
            )
            if self.psd_exporter:
                self.psd_executor.submit(self._run_deferred_psd, job_id, source, output_dir, report_payload, effective_policy)
            else:
                JOBS_TOTAL.labels(status=report.status.value).inc()
                VALIDATION_TOTAL.labels(decision=report.status.value).inc()
            for artifact in report.artifacts:
                ARTIFACTS_TOTAL.labels(media_type=artifact.media_type).inc()
            _event("CoreArtifactsReady", job_id=job_id, status=report.status.value, psd_status=report_payload["psd_export_status"])
        except (ModelProposalUnavailable, PhotopeaLiveApiUnavailable) as exc:
            self.store.update(job_id, status=JobStatus.REVIEW_REQUIRED.value, progress=100, error={"code": "required_stage_unavailable", "path": "model_or_photopea", "message": str(exc)})
            JOBS_TOTAL.labels(status="review_required").inc()
            _event("JobReviewRequired", job_id=job_id, error_type=type(exc).__name__)
        except Exception as exc:  # imperative shell boundary: unexpected bugs become explicit failed jobs
            self.store.update(job_id, status=JobStatus.FAILED.value, progress=100, error={"code": "processing_failed", "path": "job", "message": str(exc)})
            JOBS_TOTAL.labels(status="failed").inc()
            _event("JobFailed", job_id=job_id, error_type=type(exc).__name__)
        finally:
            QUEUE_DEPTH.dec()
            JOB_DURATION.observe(time.perf_counter() - started)

    def _run_deferred_psd(self, job_id: str, source: bytes, output_dir: Path, report_payload: dict[str, Any], policy) -> None:
        """Export PSD outside the bounded core job and publish an immutable update."""
        session: PhotopeaSessionClient | None = None
        try:
            source_rgba = np.asarray(Image.open(io.BytesIO(source)).convert("RGBA"), dtype=np.uint8)
            if getattr(self.psd_exporter, "supports_photopea_session", False):
                variants = tuple(report_payload.get("variants") or ("conservative", "artistic"))
                arrays = {
                    name: np.asarray(Image.open(output_dir / f"artwork_{name}.png").convert("RGBA"), dtype=np.uint8)
                    for name in variants
                }
                chosen_name = "artistic" if "artistic" in arrays else variants[0]
                chosen = arrays[chosen_name]
                mask = np.asarray(Image.open(output_dir / f"mask_{chosen_name}.png").convert("L"), dtype=np.uint8)
                if chosen.shape != source_rgba.shape:
                    raise PhotopeaLiveApiUnavailable("Photopea source and accepted candidate dimensions differ")
                revision = RasterMaskRevision(
                    revision_id=f"model-{sha256_bytes(mask.tobytes())[:16]}-r1",
                    parent_revision_id=None,
                    source_sha256=canonical_png_sha256(source_rgba),
                    checkpoint_sha256="0" * 64,
                    base_mask_sha256=sha256_bytes(mask.tobytes()),
                    result_mask_sha256=sha256_bytes(mask.tobytes()),
                    confidence=1.0,
                )
                session = PhotopeaSessionClient(self.psd_exporter.api_url, self.psd_exporter.token, timeout=self.psd_exporter.timeout)
                checkpoint = session.open(source_rgba, mask, revision)
                _accepted_mask, checkpoint_artifacts, accepted_revision = self._review_photopea_session(session, checkpoint, revision, mask)
                psd_payload, evidence = session.finalize()
                for label, filename in (("artwork", "artwork_final.png"), ("mask", "mask_final.png"), ("preview_black", "preview_final_black.png"), ("preview_navy", "preview_final_navy.png"), ("preview_blue_jean", "preview_final_blue_jean.png")):
                    path = output_dir / filename
                    path.write_bytes(checkpoint_artifacts[label])
                    report_payload["artifacts"].append({"artifact_id": filename, "name": filename, "media_type": "image/png", "size_bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())})
                psd_path = output_dir / "artwork_editable.psd"
                psd_path.write_bytes(psd_payload)
                artifact = {"artifact_id": psd_path.name, "name": psd_path.name, "media_type": "image/vnd.adobe.photoshop", "size_bytes": psd_path.stat().st_size, "sha256": sha256_bytes(psd_payload)}
                self._publish_psd_result(job_id, report_payload, artifact, verified=True, evidence=asdict(evidence), revision=asdict(accepted_revision))
                _event("PhotopeaExportCompleted", job_id=job_id, verified=True, review_revisions=accepted_revision.revision_id)
                return
            else:
                variants = tuple(report_payload.get("variants") or ("conservative", "artistic"))
                arrays = {
                    name: np.asarray(Image.open(output_dir / f"artwork_{name}.png").convert("RGBA"), dtype=np.uint8)
                    for name in variants
                }
                chosen_name = "artistic" if "artistic" in arrays else variants[0]
                chosen = arrays[chosen_name]
                mask = np.asarray(Image.open(output_dir / f"mask_{chosen_name}.png").convert("L"), dtype=np.uint8)
                export_kwargs = {"variants": arrays} if getattr(self.psd_exporter, "supports_variants", False) else {}
            psd_path = output_dir / "artwork_editable.psd"
            psd_path.write_bytes(self.psd_exporter.export(source_rgba, chosen, mask, **export_kwargs))
            artifact = {
                "artifact_id": psd_path.name,
                "name": psd_path.name,
                "media_type": "image/vnd.adobe.photoshop",
                "size_bytes": psd_path.stat().st_size,
                "sha256": sha256_bytes(psd_path.read_bytes()),
            }
            verified = bool(getattr(self.psd_exporter, "round_trip_verified", False))
            evidence = getattr(self.psd_exporter, "evidence", None)
            self._publish_psd_result(job_id, report_payload, artifact, verified=verified, evidence=asdict(evidence) if evidence else None)
            _event("PhotopeaExportCompleted", job_id=job_id, verified=verified)
        except Exception as exc:  # adapter failure is explicit; core artifacts remain available
            self._publish_psd_result(job_id, report_payload, None, error=str(exc))
            _event("PhotopeaExportFailed", job_id=job_id, error_type=type(exc).__name__)
        finally:
            if session is not None:
                session.close()

    def _review_photopea_session(self, session: PhotopeaSessionClient, checkpoint, revision: RasterMaskRevision, mask: np.ndarray):
        current_checkpoint = PhotopeaCheckpoint(checkpoint.revision_id, checkpoint.revision_id, checkpoint.source_sha256, checkpoint.checkpoint_sha256, checkpoint.mask_sha256, checkpoint.artwork_sha256, artifact_urls=checkpoint.artifact_urls)
        current_mask = mask
        current_revision = revision
        for _index in range(4):
            artifacts = session.download_checkpoint()
            if self.vision_reviewer is None:
                raise PhotopeaLiveApiUnavailable("no concrete vision reviewer is configured for the Photopea checkpoint")
            decision = self.vision_reviewer(current_checkpoint, artifacts)
            if not isinstance(decision, MaskReviewDecision):
                raise PhotopeaLiveApiUnavailable("vision reviewer returned no typed decision")
            if decision.source_sha256 != current_checkpoint.source_sha256 or decision.checkpoint_sha256 != current_checkpoint.checkpoint_sha256:
                raise PhotopeaLiveApiUnavailable("vision decision is stale or bound to another source")
            if decision.accepted:
                return current_mask, artifacts, current_revision
            if decision.revision is None or decision.correction_mask_png is None:
                raise PhotopeaLiveApiUnavailable("vision reviewer rejected checkpoint without an internal correction payload")
            with Image.open(io.BytesIO(decision.correction_mask_png)) as image:
                next_mask = np.asarray(image.convert("L"), dtype=np.uint8)
            if next_mask.shape != current_mask.shape:
                raise PhotopeaLiveApiUnavailable("vision correction dimensions differ from the source")
            if sha256_bytes(next_mask.tobytes()) != decision.revision.result_mask_sha256:
                raise PhotopeaLiveApiUnavailable("vision correction hash does not match its raster bytes")
            next_checkpoint = session.apply_revision(next_mask, decision.revision)
            current_checkpoint = PhotopeaCheckpoint(next_checkpoint.revision_id, next_checkpoint.revision_id, next_checkpoint.source_sha256, next_checkpoint.checkpoint_sha256, next_checkpoint.mask_sha256, next_checkpoint.artwork_sha256, artifact_urls=next_checkpoint.artifact_urls)
            current_mask = next_mask
            current_revision = decision.revision
        raise PhotopeaLiveApiUnavailable("Photopea review revision budget exhausted")

    def _publish_psd_result(self, job_id: str, report_payload: dict[str, Any], artifact: dict[str, Any] | None, *, verified: bool = False, evidence: dict[str, Any] | None = None, error: str | None = None, revision: dict[str, Any] | None = None) -> None:
        updated = json.loads(json.dumps(report_payload))
        validation = updated["validation"]
        stage = updated["stage_status"]
        warnings = [item for item in validation["warnings"] if item not in {"photopea_live_api_not_configured", "psd_structure_unverified"}]
        review_regions = [item for item in validation["review_regions"] if item not in {"photopea_live_api", "psd_validation"}]
        if artifact is not None:
            updated["artifacts"].append(artifact)
            stage["photopea_processing_status"] = "passed"
            stage["psd_validation_status"] = "passed" if verified else "unverified_payload"
            if evidence is not None:
                updated["photopea_evidence"] = evidence
            if revision is not None:
                updated["photopea_revision"] = revision
            if not verified:
                warnings.append("psd_structure_unverified")
                review_regions.append("psd_validation")
        else:
            stage["photopea_processing_status"] = "failed"
            stage["psd_validation_status"] = "failed"
            warnings.append(f"photopea_live_api_failed:{error or 'unknown error'}")
            review_regions.append("photopea_live_api")
        validation["warnings"] = list(dict.fromkeys(warnings))
        validation["review_regions"] = list(dict.fromkeys(review_regions))
        if validation["review_regions"] or not verified:
            updated["status"] = JobStatus.REVIEW_REQUIRED.value
            validation["status"] = JobStatus.REVIEW_REQUIRED.value
            stage["overall_status"] = JobStatus.REVIEW_REQUIRED.value
        else:
            # The core report is intentionally published as review_required
            # while the asynchronous PSD stage is pending.  Once Photopea has
            # produced pixel evidence and no review region remains, resolve
            # that provisional status instead of carrying it into the job.
            updated["status"] = JobStatus.PASSED.value
            validation["status"] = JobStatus.PASSED.value
            stage["overall_status"] = JobStatus.PASSED.value
        updated["stage_status"] = stage
        updated["psd_export_status"] = "verified" if verified else ("failed" if artifact is None else "unverified")
        report_path = self.store.job_dir(job_id) / "artifacts" / "report.json"
        report_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.store.update(job_id, status=updated["status"], progress=100, payload={"report": updated, "policy": self.store.get(job_id).payload.get("policy", {})})
        JOBS_TOTAL.labels(status=updated["status"]).inc()
        VALIDATION_TOTAL.labels(decision=updated["status"]).inc()
        if artifact:
            ARTIFACTS_TOTAL.labels(media_type=artifact["media_type"]).inc()

    def status(self, job_id: str) -> dict[str, Any]:
        if not _valid_job_id(job_id):
            raise HTTPException(status_code=400, detail={"code": "invalid_job_id", "message": "invalid job id"})
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
        if not _valid_job_id(job_id):
            raise HTTPException(status_code=400, detail={"code": "invalid_job_id", "message": "invalid job id"})
        record = self.store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "unknown job"})
        directory = self.store.job_dir(job_id) / "artifacts"
        return [
            {"name": path.name, "size_bytes": path.stat().st_size, "download_url": f"/v1/artifacts/{job_id}/{path.name}"}
            for path in sorted(directory.iterdir()) if path.is_file()
        ] if directory.exists() else []


def create_app(root: Path | None = None, token: str | None = None, psd_exporter=None, proposal_provider=None, vision_reviewer=None) -> FastAPI:
    runtime = ServiceRuntime(root or Path(os.getenv("ARTIFACT_ROOT", "artifacts/service")), token if token is not None else os.getenv("ARTWORK_SERVICE_TOKEN"), psd_exporter=psd_exporter, proposal_provider=proposal_provider, vision_reviewer=vision_reviewer)
    configured_host = os.getenv("HOST", "127.0.0.1")
    if configured_host not in {"127.0.0.1", "localhost", "::1"} and not runtime.token:
        raise RuntimeError("ARTWORK_SERVICE_TOKEN is required for non-loopback HOST")
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

    @app.middleware("http")
    async def observe_http(request, call_next):
        response = await call_next(request)
        HTTP_TOTAL.labels(request.method, request.url.path, str(response.status_code)).inc()
        return response

    @app.post("/v1/jobs", status_code=202, dependencies=[Depends(require_auth)])
    async def create_job(
        request: Request,
        source: Annotated[UploadFile, File(...)],
        policy_json: Annotated[str, Form(...)],
        manifest_json: Annotated[str, Form()] = "{}",
        idempotency_key: Annotated[str | None, Header()] = None,
        semantic_protection_mask: Annotated[UploadFile | None, File()] = None,
        removal_mask: Annotated[UploadFile | None, File()] = None,
        uncertainty_mask: Annotated[UploadFile | None, File()] = None,
        protected_reference: Annotated[UploadFile | None, File()] = None,
    ) -> JSONResponse:
        form = await request.form()
        if "photopea_mask" in form or "photopea_mask_revision" in form:
            raise HTTPException(status_code=422, detail={"code": "forbidden_final_mask_input", "message": "the public job contract accepts intent and source only; final Photopea masks are internal runtime evidence"})
        max_bytes = int(os.getenv("MAX_SOURCE_BYTES", str(100 * 1024 * 1024)))
        chunks: list[bytes] = []
        total = 0
        while chunk := await source.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail={"code": "source_too_large", "message": "source exceeds configured limit"})
            chunks.append(chunk)
        raw = b"".join(chunks)
        mask_payloads: dict[str, bytes] = {}
        for key, upload in (("semantic_protection", semantic_protection_mask), ("removable_background", removal_mask), ("uncertainty", uncertainty_mask), ("protected_reference", protected_reference)):
            if upload is not None:
                data = await upload.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise HTTPException(status_code=413, detail={"code": "mask_too_large", "message": "mask exceeds configured limit"})
                mask_payloads[key] = data
        try:
            policy = json.loads(policy_json)
            manifest = json.loads(manifest_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail={"code": "invalid_json", "message": str(exc)}) from exc
        if not isinstance(policy, dict) or not isinstance(manifest, dict):
            raise HTTPException(status_code=400, detail={"code": "invalid_manifest", "message": "policy and manifest must be JSON objects"})
        frozen = freeze_policy(policy)
        if isinstance(frozen, Err):
            raise HTTPException(status_code=422, detail={"code": frozen.error.code, "path": frozen.error.path, "message": frozen.error.message})
        result = runtime.submit(raw, policy, manifest, idempotency_key, mask_payloads)
        return JSONResponse({"job_id": result["job_id"], "status": result["status"], "poll_url": f"/v1/jobs/{result['job_id']}"}, status_code=202)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_auth)])
    def get_job(job_id: str) -> dict[str, Any]:
        return runtime.status(job_id)

    @app.get("/v1/jobs/{job_id}/artifacts", dependencies=[Depends(require_auth)])
    def list_artifacts(job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "artifacts": runtime.artifacts(job_id)}

    @app.get("/v1/artifacts/{job_id}/{name}", dependencies=[Depends(require_auth)])
    def download_artifact(job_id: str, name: str) -> FileResponse:
        if not _valid_job_id(job_id):
            raise HTTPException(status_code=400, detail={"code": "invalid_job_id", "message": "invalid job id"})
        if Path(name).name != name or name in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail={"code": "invalid_artifact_name", "message": "invalid artifact name"})
        path = runtime.store.job_dir(job_id) / "artifacts" / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "artifact_not_found", "message": "unknown artifact"})
        return FileResponse(path)

    return app


app = create_app()
