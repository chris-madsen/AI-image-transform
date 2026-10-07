from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image


class PhotopeaLiveApiUnavailable(RuntimeError):
    """The external Photopea Live outer environment is unavailable."""


@dataclass(frozen=True, slots=True)
class PhotopeaEvidence:
    """Evidence required before a PSD can be considered conformance-verified."""

    source_sha256: str
    result_mask_sha256: str
    checkpoint_sha256: str
    artwork_sha256: str
    preview_sha256: tuple[str, ...]
    reopened: bool
    required_layers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PhotopeaSessionCheckpoint:
    session_id: str
    revision_id: str
    source_sha256: str
    checkpoint_sha256: str
    mask_sha256: str
    artwork_sha256: str
    artifact_urls: tuple[tuple[str, str], ...] = ()


def _png_bytes(rgba: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _mask_png_bytes(mask: np.ndarray) -> bytes:
    values = np.asarray(mask, dtype=np.uint8)
    carrier = np.empty(values.shape + (4,), dtype=np.uint8)
    # An opaque grayscale carrier survives Photopea's clipboard transfer.
    # A white-RGB/alpha carrier is flattened to opaque white by Photopea when
    # pasted between documents, which destroys soft mask values.
    carrier[..., 0] = values
    carrier[..., 1] = values
    carrier[..., 2] = values
    carrier[..., 3] = 255
    return _png_bytes(carrier)


def _canonical_mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(mask, dtype=np.uint8).tobytes()).hexdigest()


class PhotopeaLiveApiAdapter:
    """Request PSD construction from a Photopea Live API outer environment."""

    supports_variants = False
    supports_photopea_session = True

    def __init__(self, api_url: str, token: str | None = None, timeout: float = 300.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.round_trip_verified = False
        self.evidence: PhotopeaEvidence | None = None

    def export(
        self,
        source: np.ndarray,
        artwork: np.ndarray,
        mask: np.ndarray,
        *,
        variants: Mapping[str, np.ndarray] | None = None,
        mask_revision: Mapping[str, object] | object | None = None,
        mask_plan: Mapping[str, object] | object | None = None,
    ) -> bytes:
        if mask_plan is not None:
            raise PhotopeaLiveApiUnavailable("polygon mask plans are unsupported; submit a raster mask revision")
        if mask_revision is None:
            raise PhotopeaLiveApiUnavailable("photopea_mask_revision is required for Photopea-authored masks")
        return self.export_session(source, mask, mask_revision)

    def export_session(self, source: np.ndarray, mask: np.ndarray, mask_revision: Mapping[str, object] | object) -> bytes:
        """Create and validate one Photopea document from source + raster mask."""
        boundary = "----photopea-live-api"
        revision = asdict(mask_revision) if is_dataclass(mask_revision) else dict(mask_revision)
        actual_mask_hash = _canonical_mask_sha256(mask)
        if revision.get("result_mask_sha256") != actual_mask_hash:
            raise PhotopeaLiveApiUnavailable("mask revision does not match submitted mask pixels")
        fields = {
            "request_json": json.dumps({
                "format": "psd:true",
                "workflow": "photopea_raster_mask_session",
                "source_sha256": revision.get("source_sha256"),
                "result_mask_sha256": actual_mask_hash,
            }, separators=(",", ":")),
            "mask_revision": json.dumps(revision, separators=(",", ":")),
        }
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ])
        for name, filename, content in (
            ("source", "source.png", _png_bytes(source)),
            ("mask", "mask-carrier.png", _mask_png_bytes(mask)),
        ):
            parts.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: image/png\r\n\r\n",
                content,
                b"\r\n",
            ])
        parts.append(f"--{boundary}--\r\n".encode())
        payload = self._post_multipart(boundary, parts)
        if self.evidence is None or self.evidence.source_sha256 != revision.get("source_sha256") or self.evidence.result_mask_sha256 != revision.get("result_mask_sha256") or self.evidence.checkpoint_sha256 != revision.get("checkpoint_sha256"):
            raise PhotopeaLiveApiUnavailable("Photopea evidence is not bound to the submitted raster revision")
        return payload

    def _post_multipart(self, boundary: str, parts: list[bytes]) -> bytes:
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/octet-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with urlopen(Request(f"{self.api_url}/v1/photopea/export", data=b"".join(parts), headers=headers, method="POST"), timeout=self.timeout) as response:
                payload = response.read()
                response_headers = getattr(response, "headers", {})
                roundtrip = response_headers.get("X-Photopea-Roundtrip")
                evidence_raw = response_headers.get("X-Photopea-Evidence")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise PhotopeaLiveApiUnavailable(str(exc)) from exc
        if not payload.startswith(b"8BPS"):
            raise PhotopeaLiveApiUnavailable("Photopea Live API adapter returned non-PSD data")
        self.round_trip_verified = False
        self.evidence = None
        if roundtrip != "verified" or not evidence_raw:
            raise PhotopeaLiveApiUnavailable("Photopea returned PSD without pixel round-trip evidence")
        try:
            raw = json.loads(evidence_raw)
            evidence = PhotopeaEvidence(
                source_sha256=str(raw["source_sha256"]),
                result_mask_sha256=str(raw["result_mask_sha256"]),
                checkpoint_sha256=str(raw["checkpoint_sha256"]),
                artwork_sha256=str(raw["artwork_sha256"]),
                preview_sha256=tuple(str(item) for item in raw["preview_sha256"]),
                reopened=bool(raw["reopened"]),
                required_layers=tuple(str(item) for item in raw["required_layers"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PhotopeaLiveApiUnavailable("invalid Photopea pixel evidence") from exc
        if not evidence.reopened or not evidence.result_mask_sha256 or not evidence.preview_sha256:
            raise PhotopeaLiveApiUnavailable("incomplete Photopea pixel evidence")
        self.evidence = evidence
        self.round_trip_verified = True
        return payload


class PhotopeaSessionClient:
    """Imperative client for the bounded same-document revision protocol.

    The Skill/vision adapter owns the review callback. This client only moves
    frozen raster bytes and typed revisions across the bridge; it never sends
    Photopea JavaScript and never interprets natural-language policy.
    """

    def __init__(self, api_url: str, token: str | None = None, timeout: float = 300.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self.checkpoint: PhotopeaSessionCheckpoint | None = None

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _multipart(self, fields: Mapping[str, str], files: tuple[tuple[str, str, bytes, str], ...]) -> tuple[bytes, str]:
        boundary = "----photopea-session-" + hashlib.sha256(str(id(files)).encode()).hexdigest()[:24]
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
        for name, filename, content, media_type in files:
            parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(), f"Content-Type: {media_type}\r\n\r\n".encode(), content, b"\r\n"])
        parts.append(f"--{boundary}--\r\n".encode())
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def _json_multipart(self, url: str, fields: Mapping[str, str], files: tuple[tuple[str, str, bytes, str], ...], expected_status: int) -> dict[str, object]:
        body, content_type = self._multipart(fields, files)
        try:
            with urlopen(Request(url, data=body, headers=self._headers(content_type), method="POST"), timeout=self.timeout) as response:
                if response.status != expected_status:
                    raise PhotopeaLiveApiUnavailable(f"unexpected Photopea session status: {response.status}")
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PhotopeaLiveApiUnavailable(str(exc)) from exc

    @staticmethod
    def _checkpoint(payload: Mapping[str, object]) -> PhotopeaSessionCheckpoint:
        checkpoint = payload.get("checkpoint")
        if not isinstance(checkpoint, Mapping):
            raise PhotopeaLiveApiUnavailable("Photopea session returned no checkpoint")
        try:
            return PhotopeaSessionCheckpoint(
                session_id=str(payload["session_id"]),
                revision_id=str(checkpoint["revision_id"]),
                source_sha256=str(checkpoint["source_sha256"]),
                checkpoint_sha256=str(checkpoint["checkpoint_sha256"]),
                mask_sha256=str(checkpoint["mask_sha256"]),
                artwork_sha256=str(checkpoint["artwork_sha256"]),
                artifact_urls=tuple(sorted((str(key), str(value)) for key, value in (checkpoint.get("artifact_urls") or {}).items())),
            )
        except (KeyError, TypeError) as exc:
            raise PhotopeaLiveApiUnavailable("invalid Photopea checkpoint") from exc

    def open(self, source: np.ndarray, mask: np.ndarray, revision: Mapping[str, object] | object) -> PhotopeaSessionCheckpoint:
        value = asdict(revision) if is_dataclass(revision) else dict(revision)
        payload = self._json_multipart(
            f"{self.api_url}/v1/photopea/sessions",
            {"mask_revision": json.dumps(value, separators=(",", ":"))},
            (("source", "source.png", _png_bytes(source), "image/png"), ("mask", "mask-carrier.png", _mask_png_bytes(mask), "image/png")),
            201,
        )
        checkpoint = self._checkpoint(payload)
        self.session_id = checkpoint.session_id
        self.checkpoint = checkpoint
        return checkpoint

    def apply_revision(self, mask: np.ndarray, revision: Mapping[str, object] | object) -> PhotopeaSessionCheckpoint:
        if not self.session_id:
            raise PhotopeaLiveApiUnavailable("Photopea session is not open")
        value = asdict(revision) if is_dataclass(revision) else dict(revision)
        payload = self._json_multipart(
            f"{self.api_url}/v1/photopea/sessions/{self.session_id}/revisions",
            {"mask_revision": json.dumps(value, separators=(",", ":"))},
            (("mask", "mask-carrier.png", _mask_png_bytes(mask), "image/png"),),
            200,
        )
        checkpoint = self._checkpoint(payload)
        self.checkpoint = checkpoint
        return checkpoint

    def finalize(self) -> tuple[bytes, PhotopeaEvidence]:
        if not self.session_id:
            raise PhotopeaLiveApiUnavailable("Photopea session is not open")
        try:
            with urlopen(Request(f"{self.api_url}/v1/photopea/sessions/{self.session_id}/finalize", data=b"", headers=self._headers("application/json"), method="POST"), timeout=self.timeout) as response:
                payload = response.read()
                if response.headers.get("X-Photopea-Roundtrip") != "verified":
                    raise PhotopeaLiveApiUnavailable("Photopea session finalized without pixel evidence")
                raw = json.loads(response.headers.get("X-Photopea-Evidence", "{}"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PhotopeaLiveApiUnavailable(str(exc)) from exc
        if not payload.startswith(b"8BPS"):
            raise PhotopeaLiveApiUnavailable("Photopea session returned non-PSD data")
        try:
            evidence = PhotopeaEvidence(
                source_sha256=str(raw["source_sha256"]),
                result_mask_sha256=str(raw["result_mask_sha256"]),
                checkpoint_sha256=str(raw["checkpoint_sha256"]),
                artwork_sha256=str(raw["artwork_sha256"]),
                preview_sha256=tuple(str(item) for item in raw["preview_sha256"]),
                reopened=bool(raw["reopened"]),
                required_layers=tuple(str(item) for item in raw["required_layers"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PhotopeaLiveApiUnavailable("invalid Photopea session evidence") from exc
        if self.checkpoint is not None and evidence.checkpoint_sha256 != self.checkpoint.checkpoint_sha256:
            raise PhotopeaLiveApiUnavailable("Photopea final evidence is not bound to the accepted checkpoint")
        self.session_id = None
        return payload, evidence

    def download_checkpoint(self) -> dict[str, bytes]:
        """Download exact checkpoint images before finalizing the session."""
        if self.checkpoint is None:
            raise PhotopeaLiveApiUnavailable("Photopea session has no checkpoint")
        result: dict[str, bytes] = {}
        for label, path in self.checkpoint.artifact_urls:
            url = path if path.startswith("http") else f"{self.api_url}{path}"
            try:
                with urlopen(Request(url, headers=self._headers(), method="GET"), timeout=self.timeout) as response:
                    result[label] = response.read()
            except (HTTPError, URLError, TimeoutError) as exc:
                raise PhotopeaLiveApiUnavailable(f"checkpoint artifact {label} unavailable: {exc}") from exc
        required = {"artwork", "mask", "preview_black", "preview_navy", "preview_blue_jean"}
        if set(result) != required:
            raise PhotopeaLiveApiUnavailable("Photopea checkpoint did not expose all required review artifacts")
        return result

    def close(self) -> None:
        if not self.session_id:
            return
        try:
            request = Request(f"{self.api_url}/v1/photopea/sessions/{self.session_id}", headers=self._headers(), method="DELETE")
            with urlopen(request, timeout=min(self.timeout, 10)):
                pass
        except (HTTPError, URLError, TimeoutError):
            pass
        finally:
            self.session_id = None
