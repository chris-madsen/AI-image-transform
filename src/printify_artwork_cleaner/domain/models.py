from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from enum import StrEnum
from typing import Any, Mapping, TypeVar


T = TypeVar("T")


class JobStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    PASSED = "passed"
    REFUSED = "refused"
    FAILED = "failed"


class EdgeStrategy(StrEnum):
    AUTO_PRINT_SAFE = "auto_print_safe"
    BINARY_ALPHA = "binary_alpha"
    CONTROLLED_SOFT_ALPHA = "controlled_soft_alpha"
    HALFTONE = "halftone"


class ProcessingMode(StrEnum):
    INSPECT = "inspect"
    CLEAN_EDGE = "clean_edge"
    REMOVE_BAKED_BACKGROUND = "remove_baked_background"
    PRESERVE_SOFT_FADE = "preserve_soft_fade"
    HALFTONE_DARK_GARMENT = "halftone_dark_garment"
    MANUAL_MASK = "manual_mask"
    AUTO = "auto"


class VariantName(StrEnum):
    CONSERVATIVE = "conservative"
    ARTISTIC = "artistic"
    HALFTONE = "halftone"
    BINARY_ALPHA = "binary_alpha"
    CONTROLLED_SOFT_ALPHA = "controlled_soft_alpha"


@dataclass(frozen=True, slots=True)
class DomainError:
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T


@dataclass(frozen=True, slots=True)
class Err:
    error: DomainError


Result = Ok[T] | Err


@dataclass(frozen=True, slots=True)
class ProtectedRegion:
    """Normalized [0, 1] rectangle supplied by the agent or a reviewer."""

    x: float
    y: float
    width: float
    height: float
    label: str = "protected"

    def pixels(self, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        left = max(0, min(image_width, round(self.x * image_width)))
        top = max(0, min(image_height, round(self.y * image_height)))
        right = max(left, min(image_width, round((self.x + self.width) * image_width)))
        bottom = max(top, min(image_height, round((self.y + self.height) * image_height)))
        return left, top, right, bottom


@dataclass(frozen=True, slots=True)
class VisualQualityAssessment:
    """Frozen multimodal/vision judgement supplied by the agent boundary."""

    reference_id: str
    overall_score: float
    subject_integrity: float
    intentional_detail_score: float
    edge_naturalness: float
    artifact_free_score: float
    confidence: float
    reviewer_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaskTuning:
    """Per-artwork parameters selected by the vision/agent boundary.

    These values are deliberately not global configuration.  They are frozen
    together with the processing policy after the artwork has been inspected.
    """

    background_tolerance: int
    fade_low_distance: int
    fade_full_distance: int
    fade_band_radius: int
    confidence: float
    decision_id: str


Polygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class PhotopeaMaskPlan:
    """Typed selection plan executed inside the Photopea document."""

    revision_id: str
    subject_polygons: tuple[Polygon, ...]
    remove_polygons: tuple[Polygon, ...] = ()
    protect_polygons: tuple[Polygon, ...] = ()
    feather_px: int = 0
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ProcessingPolicy:
    primary_subject: str = ""
    must_keep: tuple[str, ...] = ()
    keep_if_intentional: tuple[str, ...] = ()
    remove_only: tuple[str, ...] = ()
    target_garments: tuple[str, ...] = ("black", "white", "navy", "blue_jean")
    edge_strategy: EdgeStrategy = EdgeStrategy.AUTO_PRINT_SAFE
    requested_variants: tuple[str, ...] = ("conservative", "artistic")
    mode: ProcessingMode = ProcessingMode.AUTO
    protected_regions: tuple[ProtectedRegion, ...] = ()
    background_tolerance: int | None = None
    halftone_cell: int = 8
    canvas_width: int | None = None
    canvas_height: int | None = None
    canvas_dpi: int = 300
    canvas_margin: int = 0
    visual_quality: VisualQualityAssessment | None = None
    mask_tuning: MaskTuning | None = None
    photopea_mask_plan: PhotopeaMaskPlan | None = None

    @property
    def effective_background_tolerance(self) -> int:
        return self.mask_tuning.background_tolerance if self.mask_tuning else (self.background_tolerance if self.background_tolerance is not None else 8)


@dataclass(frozen=True, slots=True)
class ImageGeometry:
    width: int
    height: int
    mode: str
    has_alpha: bool


@dataclass(frozen=True, slots=True)
class AlphaProfile:
    total: int
    zero: int
    partial: int
    full: int
    unique_levels: int
    hidden_rgb_pixels: int


@dataclass(frozen=True, slots=True)
class ArtworkInspection:
    geometry: ImageGeometry
    alpha: AlphaProfile
    classification: str
    border_connected_pixels: int
    crop_risk: bool
    source_sha256: str
    canonical_pixels_sha256: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaskRevision:
    revision_id: str
    parent_id: str | None
    mask_sha256: str
    operations: tuple[str, ...] = ()
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ResolvedMaskBundle:
    """Frozen pixel-level intent. Text labels alone never become protection."""

    semantic_protection: Any | None = None
    removable_background: Any | None = None
    uncertainty: Any | None = None
    manual_corrections: Any | None = None
    protected_reference: Any | None = None
    confidence: float = 0.0
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StageStatus:
    ai_mask_status: str
    photopea_processing_status: str
    psd_validation_status: str
    png_validation_status: str
    overall_status: JobStatus


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: JobStatus
    halo_score: float
    frame_score: float
    protected_detail_score: float
    changed_pixels: int
    protected_alpha_loss_pixels: int = 0
    protected_rgb_diff_pixels: int = 0
    unauthorized_alpha_removal_pixels: int = 0
    warnings: tuple[str, ...] = ()
    review_regions: tuple[str, ...] = ()
    visual_quality_score: float = 0.0
    edge_fragmentation_score: float = 0.0
    visual_quality_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class Artifact:
    artifact_id: str
    name: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ProcessingReport:
    status: JobStatus
    inspection: ArtworkInspection
    validation: ValidationResult
    pipeline_version: str
    edge_strategy: str
    variants: tuple[str, ...]
    artifacts: tuple[Artifact, ...] = ()
    changed_rgb: bool = False
    stage_status: StageStatus | None = None
    variant_validations: dict[str, ValidationResult] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "pipeline_version": self.pipeline_version,
            "edge_strategy": self.edge_strategy,
            "variants": list(self.variants),
            "changed_rgb": self.changed_rgb,
            "inspection": {
                "geometry": asdict(self.inspection.geometry),
                "alpha": asdict(self.inspection.alpha),
                "classification": self.inspection.classification,
                "border_connected_pixels": self.inspection.border_connected_pixels,
                "crop_risk": self.inspection.crop_risk,
                "source_sha256": self.inspection.source_sha256,
                "canonical_pixels_sha256": self.inspection.canonical_pixels_sha256,
                "warnings": list(self.inspection.warnings),
            },
            "validation": {
                "status": self.validation.status.value,
                "halo_score": self.validation.halo_score,
                "frame_score": self.validation.frame_score,
                "protected_detail_score": self.validation.protected_detail_score,
                "changed_pixels": self.validation.changed_pixels,
                "protected_alpha_loss_pixels": self.validation.protected_alpha_loss_pixels,
                "protected_rgb_diff_pixels": self.validation.protected_rgb_diff_pixels,
                "unauthorized_alpha_removal_pixels": self.validation.unauthorized_alpha_removal_pixels,
                "visual_quality_score": self.validation.visual_quality_score,
                "edge_fragmentation_score": self.validation.edge_fragmentation_score,
                "visual_quality_confidence": self.validation.visual_quality_confidence,
                "warnings": list(self.validation.warnings),
                "review_regions": list(self.validation.review_regions),
            },
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
            "stage_status": {
                "ai_mask_status": self.stage_status.ai_mask_status,
                "photopea_processing_status": self.stage_status.photopea_processing_status,
                "psd_validation_status": self.stage_status.psd_validation_status,
                "png_validation_status": self.stage_status.png_validation_status,
                "overall_status": self.stage_status.overall_status.value,
            } if self.stage_status else None,
            "variant_validations": {
                name: {**asdict(value), "status": value.status.value}
                for name, value in (self.variant_validations or {}).items()
            },
        }


def as_string_tuple(value: Any, path: str) -> Result[tuple[str, ...]]:
    if value is None:
        return Ok(())
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return Err(DomainError("type", path, "expected a list of non-empty strings"))
    return Ok(tuple(item.strip() for item in value))


def _freeze_polygons(value: Any, path: str) -> Result[tuple[Polygon, ...]]:
    if value is None:
        return Ok(())
    if not isinstance(value, list) or len(value) > 128:
        return Err(DomainError("type", path, "expected at most 128 polygons"))
    polygons: list[Polygon] = []
    for polygon_index, raw_polygon in enumerate(value):
        if not isinstance(raw_polygon, list) or not 3 <= len(raw_polygon) <= 4096:
            return Err(DomainError("type", f"{path}[{polygon_index}]", "expected 3..4096 points"))
        points: list[tuple[float, float]] = []
        for point_index, raw_point in enumerate(raw_polygon):
            if not isinstance(raw_point, list) or len(raw_point) != 2:
                return Err(DomainError("type", f"{path}[{polygon_index}][{point_index}]", "expected [x, y]"))
            try:
                x, y = float(raw_point[0]), float(raw_point[1])
            except (TypeError, ValueError):
                return Err(DomainError("value", f"{path}[{polygon_index}][{point_index}]", "coordinates must be numeric"))
            if not all(isfinite(value) and 0 <= value <= 1 for value in (x, y)):
                return Err(DomainError("value", f"{path}[{polygon_index}][{point_index}]", "coordinates must be normalized to [0, 1]"))
            points.append((x, y))
        polygons.append(tuple(points))
    return Ok(tuple(polygons))


def freeze_policy(raw: Mapping[str, Any] | None) -> Result[ProcessingPolicy]:
    raw = raw or {}
    if not isinstance(raw, Mapping):
        return Err(DomainError("type", "policy", "expected an object"))

    fields = (
        ("must_keep", "policy.must_keep"),
        ("keep_if_intentional", "policy.keep_if_intentional"),
        ("remove_only", "policy.remove_only"),
        ("target_garments", "policy.target_garments"),
        ("requested_variants", "policy.requested_variants"),
    )
    values: dict[str, tuple[str, ...]] = {}
    for key, path in fields:
        parsed = as_string_tuple(raw.get(key), path)
        if isinstance(parsed, Err):
            return parsed
        values[key] = parsed.value

    allowed_variants = {item.value for item in VariantName}
    unknown_variants = [item for item in values["requested_variants"] if item not in allowed_variants]
    if unknown_variants:
        return Err(DomainError("value", "policy.requested_variants", f"unsupported variants: {unknown_variants!r}"))

    strategy_raw = raw.get("edge_strategy", EdgeStrategy.AUTO_PRINT_SAFE.value)
    try:
        strategy = EdgeStrategy(strategy_raw)
    except ValueError:
        return Err(DomainError("value", "policy.edge_strategy", f"unsupported strategy: {strategy_raw!r}"))

    mode_raw = raw.get("mode", ProcessingMode.AUTO.value)
    try:
        mode = ProcessingMode(mode_raw)
    except ValueError:
        return Err(DomainError("value", "policy.mode", f"unsupported mode: {mode_raw!r}"))

    tolerance = raw.get("background_tolerance")
    if tolerance is not None and (not isinstance(tolerance, int) or not 0 <= tolerance <= 128):
        return Err(DomainError("value", "policy.background_tolerance", "must be an integer in [0, 128] when supplied"))
    cell = raw.get("halftone_cell", 8)
    if not isinstance(cell, int) or cell < 2 or cell > 64:
        return Err(DomainError("value", "policy.halftone_cell", "must be an integer in [2, 64]"))
    canvas_width = raw.get("canvas_width")
    canvas_height = raw.get("canvas_height")
    if (canvas_width is None) != (canvas_height is None) or any(value is not None and (not isinstance(value, int) or value < 1 or value > 20000) for value in (canvas_width, canvas_height)):
        return Err(DomainError("value", "policy.canvas", "width and height must both be integers in [1, 20000]"))
    canvas_dpi = raw.get("canvas_dpi", 300)
    canvas_margin = raw.get("canvas_margin", 0)
    if not isinstance(canvas_dpi, int) or not 1 <= canvas_dpi <= 2400:
        return Err(DomainError("value", "policy.canvas_dpi", "must be an integer in [1, 2400]"))
    if not isinstance(canvas_margin, int) or canvas_margin < 0:
        return Err(DomainError("value", "policy.canvas_margin", "must be a non-negative integer"))

    mask_tuning: MaskTuning | None = None
    raw_tuning = raw.get("mask_tuning")
    if raw_tuning is not None:
        if not isinstance(raw_tuning, Mapping):
            return Err(DomainError("type", "policy.mask_tuning", "expected an object"))
        try:
            tuning_values = {
                "background_tolerance": int(raw_tuning["background_tolerance"]),
                "fade_low_distance": int(raw_tuning["fade_low_distance"]),
                "fade_full_distance": int(raw_tuning["fade_full_distance"]),
                "fade_band_radius": int(raw_tuning["fade_band_radius"]),
                "confidence": float(raw_tuning["confidence"]),
            }
            decision_id = str(raw_tuning["decision_id"]).strip()
        except (KeyError, TypeError, ValueError):
            return Err(DomainError("value", "policy.mask_tuning", "missing or invalid tuning fields"))
        if not 0 <= tuning_values["background_tolerance"] <= 128:
            return Err(DomainError("value", "policy.mask_tuning.background_tolerance", "must be in [0, 128]"))
        if not 0 <= tuning_values["fade_low_distance"] < tuning_values["fade_full_distance"] <= 255:
            return Err(DomainError("value", "policy.mask_tuning.fade_distance", "must satisfy 0 <= low < full <= 255"))
        if not 0 <= tuning_values["fade_band_radius"] <= 32:
            return Err(DomainError("value", "policy.mask_tuning.fade_band_radius", "must be in [0, 32]"))
        if not decision_id or not isfinite(tuning_values["confidence"]) or not 0 <= tuning_values["confidence"] <= 1:
            return Err(DomainError("value", "policy.mask_tuning", "decision_id and confidence must be valid"))
        mask_tuning = MaskTuning(decision_id=decision_id, **tuning_values)

    photopea_mask_plan: PhotopeaMaskPlan | None = None
    raw_plan = raw.get("photopea_mask_plan")
    if raw_plan is not None:
        if not isinstance(raw_plan, Mapping):
            return Err(DomainError("type", "policy.photopea_mask_plan", "expected an object"))
        try:
            revision_id = str(raw_plan["revision_id"]).strip()
            feather_px = int(raw_plan.get("feather_px", 0))
            confidence = float(raw_plan["confidence"])
        except (KeyError, TypeError, ValueError):
            return Err(DomainError("value", "policy.photopea_mask_plan", "missing or invalid plan fields"))
        subject = _freeze_polygons(raw_plan.get("subject_polygons"), "policy.photopea_mask_plan.subject_polygons")
        remove = _freeze_polygons(raw_plan.get("remove_polygons", []), "policy.photopea_mask_plan.remove_polygons")
        protect = _freeze_polygons(raw_plan.get("protect_polygons", []), "policy.photopea_mask_plan.protect_polygons")
        if any(isinstance(item, Err) for item in (subject, remove, protect)):
            return next(item for item in (subject, remove, protect) if isinstance(item, Err))
        if not revision_id or not subject.value:
            return Err(DomainError("value", "policy.photopea_mask_plan", "revision_id and subject_polygons are required"))
        if not 0 <= feather_px <= 256:
            return Err(DomainError("value", "policy.photopea_mask_plan.feather_px", "must be in [0, 256]"))
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            return Err(DomainError("value", "policy.photopea_mask_plan.confidence", "must be in [0, 1]"))
        photopea_mask_plan = PhotopeaMaskPlan(revision_id, subject.value, remove.value, protect.value, feather_px, confidence)

    visual_quality: VisualQualityAssessment | None = None
    raw_quality = raw.get("visual_quality")
    if raw_quality is not None:
        if not isinstance(raw_quality, Mapping):
            return Err(DomainError("type", "policy.visual_quality", "expected an object"))
        try:
            quality_values = {
                key: float(raw_quality[key])
                for key in ("overall_score", "subject_integrity", "intentional_detail_score", "edge_naturalness", "artifact_free_score", "confidence")
            }
            reference_id = str(raw_quality["reference_id"]).strip()
        except (KeyError, TypeError, ValueError):
            return Err(DomainError("value", "policy.visual_quality", "missing or invalid assessment fields"))
        if not reference_id or not all(isfinite(value) and 0 <= value <= 1 for value in quality_values.values()):
            return Err(DomainError("value", "policy.visual_quality", "reference_id and scores must be valid; scores must be in [0, 1]"))
        notes = raw_quality.get("reviewer_notes", [])
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            return Err(DomainError("type", "policy.visual_quality.reviewer_notes", "expected a list of strings"))
        visual_quality = VisualQualityAssessment(reference_id=reference_id, reviewer_notes=tuple(notes), **quality_values)

    regions: list[ProtectedRegion] = []
    raw_regions = raw.get("protected_regions", [])
    if not isinstance(raw_regions, list):
        return Err(DomainError("type", "policy.protected_regions", "expected a list"))
    for index, item in enumerate(raw_regions):
        if not isinstance(item, Mapping):
            return Err(DomainError("type", f"policy.protected_regions[{index}]", "expected an object"))
        try:
            region = ProtectedRegion(
                x=float(item["x"]), y=float(item["y"]),
                width=float(item["width"]), height=float(item["height"]),
                label=str(item.get("label", "protected")),
            )
        except (KeyError, TypeError, ValueError):
            return Err(DomainError("value", f"policy.protected_regions[{index}]", "invalid rectangle"))
        if not all(0 <= value <= 1 for value in (region.x, region.y, region.width, region.height)):
            return Err(DomainError("value", f"policy.protected_regions[{index}]", "coordinates must be normalized"))
        if region.x + region.width > 1 or region.y + region.height > 1:
            return Err(DomainError("value", f"policy.protected_regions[{index}]", "rectangle exceeds image bounds"))
        regions.append(region)

    return Ok(ProcessingPolicy(
        primary_subject=str(raw.get("primary_subject", "")).strip(),
        must_keep=values["must_keep"],
        keep_if_intentional=values["keep_if_intentional"],
        remove_only=values["remove_only"],
        target_garments=values["target_garments"] or ("black", "white", "navy", "blue_jean"),
        edge_strategy=strategy,
        requested_variants=values["requested_variants"] or ("conservative", "artistic"),
        mode=mode,
        protected_regions=tuple(regions),
        background_tolerance=tolerance,
        halftone_cell=cell,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        canvas_dpi=canvas_dpi,
        canvas_margin=canvas_margin,
        visual_quality=visual_quality,
        mask_tuning=mask_tuning,
        photopea_mask_plan=photopea_mask_plan,
    ))
