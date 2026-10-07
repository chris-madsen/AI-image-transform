from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

from ..domain.image_math import canonical_rgba_png_bytes
from ..domain.models import MaskProposalBundle, MaskTuning, ModelEvidence, ProcessingPolicy, ResolvedMaskBundle, VisualQualityAssessment


class ModelProposalUnavailable(RuntimeError):
    """A declared specialized proposal provider could not produce evidence."""


@dataclass(frozen=True, slots=True)
class ProposalResponse:
    alpha: np.ndarray
    protection: np.ndarray
    uncertainty: np.ndarray
    evidence: ModelEvidence
    mask_tuning: MaskTuning | None = None
    visual_quality: VisualQualityAssessment | None = None


@dataclass(frozen=True, slots=True)
class ProtectionResponse:
    protection: np.ndarray
    uncertainty: np.ndarray
    evidence: ModelEvidence


def derive_mask_tuning(source: np.ndarray, alpha: np.ndarray, source_sha256: str, decision_prefix: str = "model-preflight") -> MaskTuning:
    """Derive bounded Photopea-style selection tuning from one artwork."""

    rgb = np.asarray(source[..., :3], dtype=np.int16)
    border = np.concatenate((rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]), axis=0)
    background_colour = np.median(border, axis=0).astype(np.int16)
    colour_distance = np.max(np.abs(rgb - background_colour), axis=-1)
    model_alpha = np.asarray(alpha, dtype=np.uint8)
    transition = (model_alpha > 26) & (model_alpha < 229)
    boundary_distances = colour_distance[transition]
    border_spread = float(np.percentile(np.max(np.abs(border - background_colour), axis=1), 75))
    tolerance = float(np.percentile(boundary_distances, 50)) if boundary_distances.size else border_spread
    partial = model_alpha[(model_alpha > 0) & (model_alpha < 255)]
    partial_mid = float(np.percentile(partial, 50)) if partial.size else 128.0
    return MaskTuning(
        background_tolerance=int(np.clip(round(tolerance), 2, 32)),
        fade_low_distance=int(np.clip(round(max(1.0, partial_mid * 0.08)), 1, 254)),
        fade_full_distance=int(np.clip(round(max(2.0, partial_mid * 0.40)), 2, 255)),
        fade_band_radius=int(np.clip(round(np.sqrt(max(1, partial.size)) / 100), 1, 32)),
        confidence=0.5,
        decision_id=f"{decision_prefix}-{source_sha256[:16]}",
        source_sha256=source_sha256,
    )


def _png_bytes(source: np.ndarray) -> bytes:
    return canonical_rgba_png_bytes(source)


def _decode_mask(value: str, shape: tuple[int, int]) -> np.ndarray:
    try:
        raw = base64.b64decode(value, validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            result = np.asarray(image.convert("L"), dtype=np.uint8)
    except (ValueError, OSError) as exc:
        raise ModelProposalUnavailable("model returned an invalid base64 PNG mask") from exc
    if result.shape != shape:
        raise ModelProposalUnavailable(f"model mask dimensions {result.shape} do not match source {shape}")
    return result


def _parse_runtime_evidence(body: dict[str, object], source_sha256: str, provider: str) -> tuple[MaskTuning, VisualQualityAssessment]:
    tuning = body.get("mask_tuning")
    quality = body.get("visual_quality")
    if not isinstance(tuning, dict) or not isinstance(quality, dict):
        raise ModelProposalUnavailable(f"{provider} response lacks per-artwork mask_tuning or visual_quality")
    try:
        mask_tuning = MaskTuning(
            background_tolerance=int(tuning["background_tolerance"]),
            fade_low_distance=int(tuning["fade_low_distance"]),
            fade_full_distance=int(tuning["fade_full_distance"]),
            fade_band_radius=int(tuning["fade_band_radius"]),
            confidence=float(tuning["confidence"]),
            decision_id=str(tuning["decision_id"]),
            source_sha256=str(tuning.get("source_sha256", source_sha256)),
        )
        visual_quality = VisualQualityAssessment(
            reference_id=str(quality["reference_id"]),
            overall_score=float(quality["overall_score"]),
            subject_integrity=float(quality["subject_integrity"]),
            intentional_detail_score=float(quality["intentional_detail_score"]),
            edge_naturalness=float(quality["edge_naturalness"]),
            artifact_free_score=float(quality["artifact_free_score"]),
            confidence=float(quality["confidence"]),
            source_sha256=str(quality.get("source_sha256", source_sha256)),
            checkpoint_sha256=str(quality.get("checkpoint_sha256", "")),
            reviewer_notes=tuple(str(item) for item in quality.get("reviewer_notes", ())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelProposalUnavailable(f"{provider} returned invalid runtime evidence") from exc
    if mask_tuning.source_sha256 != source_sha256 or visual_quality.source_sha256 != source_sha256:
        raise ModelProposalUnavailable(f"{provider} runtime evidence is bound to another source")
    scores = (
        mask_tuning.confidence,
        visual_quality.overall_score,
        visual_quality.subject_integrity,
        visual_quality.intentional_detail_score,
        visual_quality.edge_naturalness,
        visual_quality.artifact_free_score,
        visual_quality.confidence,
    )
    if not 0 <= mask_tuning.background_tolerance <= 128 or not 0 <= mask_tuning.fade_low_distance < mask_tuning.fade_full_distance <= 255 or not 0 <= mask_tuning.fade_band_radius <= 32 or not all(0 <= score <= 1 for score in scores):
        raise ModelProposalUnavailable(f"{provider} runtime evidence is outside allowed bounds")
    return mask_tuning, visual_quality


class HttpMattingProvider:
    """Adapter for a pinned BiRefNet/BEN2 model-serving endpoint.

    The model server is deliberately outside the domain core. Its response is
    accepted only when it carries model identity, license and weights hash.
    No endpoint means no silent heuristic fallback.
    """

    def __init__(self, *, provider: str, model: str, endpoint: str, version: str, license: str, weights_sha256: str, timeout: float = 120.0) -> None:
        if not endpoint or not version or not license or not re_hex64(weights_sha256.lower()):
            raise ValueError("model provider requires endpoint, version, license and a SHA-256 weights hash")
        self.provider = provider
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.version = version
        self.license = license
        self.weights_sha256 = weights_sha256.lower()
        self.timeout = timeout

    def propose(self, source: np.ndarray, policy: ProcessingPolicy) -> ProposalResponse:
        payload = _png_bytes(source)
        request = Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "image/png", "Accept": "application/json", "X-Model-Policy": json.dumps({"primary_subject": policy.primary_subject, "must_keep": policy.must_keep, "remove_only": policy.remove_only})},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelProposalUnavailable(f"{self.provider} proposal endpoint unavailable: {exc}") from exc
        expected_shape = source.shape[:2]
        source_sha256 = hashlib.sha256(payload).hexdigest()
        if not isinstance(body, dict) or not body.get("alpha_png_base64"):
            raise ModelProposalUnavailable(f"{self.provider} response has no alpha_png_base64")
        required_metadata = ("model", "version", "license", "weights_sha256")
        if any(not isinstance(body.get(key), str) or not str(body[key]).strip() for key in required_metadata):
            raise ModelProposalUnavailable(f"{self.provider} response lacks explicit model metadata")
        evidence = ModelEvidence(
            provider=self.provider,
            model=str(body["model"]),
            version=str(body["version"]),
            license=str(body["license"]),
            weights_sha256=str(body["weights_sha256"]).lower(),
            proposal_sha256=str(body.get("proposal_sha256", "")),
        )
        declared = (self.model, self.version, self.license, self.weights_sha256)
        returned = (evidence.model, evidence.version, evidence.license, evidence.weights_sha256)
        if returned != declared or not re_hex64(evidence.weights_sha256):
            raise ModelProposalUnavailable(f"{self.provider} returned model metadata that differs from its deployment pin")
        mask_tuning, visual_quality = _parse_runtime_evidence(body, source_sha256, self.provider)
        alpha_b64 = str(body["alpha_png_base64"])
        alpha = _decode_mask(alpha_b64, expected_shape)
        protection = _decode_mask(str(body.get("protection_png_base64", alpha_b64)), expected_shape) > 0
        uncertainty = _decode_mask(str(body.get("uncertainty_png_base64", alpha_b64)), expected_shape)
        proposal_hash = hashlib.sha256(alpha.tobytes() + protection.tobytes() + uncertainty.tobytes()).hexdigest()
        if evidence.proposal_sha256 and evidence.proposal_sha256 != proposal_hash:
            raise ModelProposalUnavailable(f"{self.provider} proposal hash mismatch")
        return ProposalResponse(alpha, protection, uncertainty, ModelEvidence(evidence.provider, evidence.model, evidence.version, evidence.license, evidence.weights_sha256, proposal_hash), mask_tuning, visual_quality)


class BiRefNetHRMattingProvider(HttpMattingProvider):
    def __init__(self, endpoint: str, **metadata: str) -> None:
        super().__init__(provider="birefnet", model="BiRefNet HR-matting", endpoint=endpoint, **metadata)


class BEN2MattingProvider(HttpMattingProvider):
    def __init__(self, endpoint: str, **metadata: str) -> None:
        super().__init__(provider="ben2", model="BEN2", endpoint=endpoint, **metadata)


class HttpProtectionProvider:
    """Adapter for a pinned semantic-protection model such as SAM 2.1.

    Protection is deliberately a separate port from matting alpha.  The core
    uses it only to prevent edge-connected cleanup from removing intentional
    subject/detail pixels; it never treats a SAM proposal as a final alpha.
    """

    def __init__(self, *, provider: str, model: str, endpoint: str, version: str, license: str, weights_sha256: str, timeout: float = 120.0) -> None:
        if not endpoint or not version or not license or not re_hex64(weights_sha256.lower()):
            raise ValueError("protection provider requires endpoint, version, license and a SHA-256 weights hash")
        self.provider = provider
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.version = version
        self.license = license
        self.weights_sha256 = weights_sha256.lower()
        self.timeout = timeout

    def propose(self, source: np.ndarray, policy: ProcessingPolicy) -> ProtectionResponse:
        payload = _png_bytes(source)
        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Content-Type": "image/png",
                "Accept": "application/json",
                "X-Model-Policy": json.dumps({"primary_subject": policy.primary_subject, "must_keep": policy.must_keep, "keep_if_intentional": policy.keep_if_intentional}),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelProposalUnavailable(f"{self.provider} protection endpoint unavailable: {exc}") from exc
        expected_shape = source.shape[:2]
        source_sha256 = hashlib.sha256(payload).hexdigest()
        required_metadata = ("model", "version", "license", "weights_sha256", "source_sha256", "protection_png_base64")
        if any(not isinstance(body.get(key), str) or not str(body[key]).strip() for key in required_metadata):
            raise ModelProposalUnavailable(f"{self.provider} response lacks explicit protection metadata")
        evidence = ModelEvidence(
            provider=self.provider,
            model=str(body["model"]),
            version=str(body["version"]),
            license=str(body["license"]),
            weights_sha256=str(body["weights_sha256"]).lower(),
            proposal_sha256=str(body.get("proposal_sha256", "")),
        )
        declared = (self.model, self.version, self.license, self.weights_sha256)
        returned = (evidence.model, evidence.version, evidence.license, evidence.weights_sha256)
        if returned != declared or not re_hex64(evidence.weights_sha256):
            raise ModelProposalUnavailable(f"{self.provider} returned model metadata that differs from its deployment pin")
        if str(body["source_sha256"]) != source_sha256:
            raise ModelProposalUnavailable(f"{self.provider} protection response is bound to another source")
        protection = _decode_mask(str(body["protection_png_base64"]), expected_shape) > 0
        uncertainty = _decode_mask(str(body.get("uncertainty_png_base64", body["protection_png_base64"])), expected_shape)
        proposal_hash = hashlib.sha256(protection.tobytes() + uncertainty.tobytes()).hexdigest()
        if evidence.proposal_sha256 and evidence.proposal_sha256 != proposal_hash:
            raise ModelProposalUnavailable(f"{self.provider} protection hash mismatch")
        return ProtectionResponse(protection, uncertainty, ModelEvidence(evidence.provider, evidence.model, evidence.version, evidence.license, evidence.weights_sha256, proposal_hash))


class SAM21ProtectionProvider(HttpProtectionProvider):
    def __init__(self, endpoint: str, **metadata: str) -> None:
        super().__init__(provider="sam2", model="SAM 2.1", endpoint=endpoint, **metadata)


class ConsensusMattingProvider:
    """Require two independent proposals and produce a conservative consensus."""

    def __init__(self, primary: HttpMattingProvider, secondary: HttpMattingProvider, protection_provider: HttpProtectionProvider | None = None) -> None:
        self.primary = primary
        self.secondary = secondary
        self.protection_provider = protection_provider

    def propose(self, source: np.ndarray, policy: ProcessingPolicy) -> MaskProposalBundle:
        first = self.primary.propose(source, policy)
        second = self.secondary.propose(source, policy)
        alpha = ((first.alpha.astype(np.uint16) + second.alpha.astype(np.uint16)) // 2).astype(np.uint8)
        protection = first.protection | second.protection
        uncertainty = np.maximum(first.uncertainty, second.uncertainty)
        evidence = [first.evidence, second.evidence]
        if self.protection_provider is not None:
            semantic = self.protection_provider.propose(source, policy)
            protection |= semantic.protection
            uncertainty = np.maximum(uncertainty, semantic.uncertainty)
            evidence.append(semantic.evidence)
        removal = alpha < 255
        confidence = float(np.mean(255 - np.abs(first.alpha.astype(np.int16) - second.alpha.astype(np.int16))) / 255)
        return MaskProposalBundle(
            resolved_masks=ResolvedMaskBundle(
                semantic_protection=protection,
                removable_background=removal,
                uncertainty=uncertainty,
                proposed_alpha=alpha,
                provenance=tuple(item.provider for item in evidence) + ("consensus",),
                confidence=confidence,
            ),
            evidence=tuple(evidence),
            confidence=confidence,
            mask_tuning=first.mask_tuning,
            visual_quality=first.visual_quality,
        )


def re_hex64(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def configured_consensus_provider() -> ConsensusMattingProvider | None:
    primary = os.getenv("BIREFNET_ENDPOINT")
    secondary = os.getenv("BEN2_ENDPOINT")
    if not primary or not secondary:
        return None
    primary_metadata = {
        "version": os.getenv("BIREFNET_MODEL_VERSION", ""),
        "license": os.getenv("BIREFNET_MODEL_LICENSE", ""),
        "weights_sha256": os.getenv("BIREFNET_WEIGHTS_SHA256", ""),
    }
    secondary_metadata = {
        "version": os.getenv("BEN2_MODEL_VERSION", ""),
        "license": os.getenv("BEN2_MODEL_LICENSE", ""),
        "weights_sha256": os.getenv("BEN2_WEIGHTS_SHA256", ""),
    }
    protection_provider = None
    sam_endpoint = os.getenv("SAM2_ENDPOINT")
    sam_metadata = {
        "version": os.getenv("SAM2_MODEL_VERSION", ""),
        "license": os.getenv("SAM2_MODEL_LICENSE", ""),
        "weights_sha256": os.getenv("SAM2_WEIGHTS_SHA256", ""),
    }
    try:
        if sam_endpoint:
            protection_provider = SAM21ProtectionProvider(sam_endpoint, **sam_metadata)
        return ConsensusMattingProvider(
            BiRefNetHRMattingProvider(primary, **primary_metadata),
            BEN2MattingProvider(secondary, **secondary_metadata),
            protection_provider=protection_provider,
        )
    except ValueError:
        return None
