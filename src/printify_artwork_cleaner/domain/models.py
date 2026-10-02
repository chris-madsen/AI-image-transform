from __future__ import annotations

from dataclasses import asdict, dataclass
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
    background_tolerance: int = 24
    halftone_cell: int = 8


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
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaskRevision:
    revision_id: str
    parent_id: str | None
    mask_sha256: str
    operations: tuple[str, ...] = ()
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: JobStatus
    halo_score: float
    frame_score: float
    protected_detail_score: float
    changed_pixels: int
    warnings: tuple[str, ...] = ()
    review_regions: tuple[str, ...] = ()


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
                "warnings": list(self.inspection.warnings),
            },
            "validation": {
                "status": self.validation.status.value,
                "halo_score": self.validation.halo_score,
                "frame_score": self.validation.frame_score,
                "protected_detail_score": self.validation.protected_detail_score,
                "changed_pixels": self.validation.changed_pixels,
                "warnings": list(self.validation.warnings),
                "review_regions": list(self.validation.review_regions),
            },
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
        }


def as_string_tuple(value: Any, path: str) -> Result[tuple[str, ...]]:
    if value is None:
        return Ok(())
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return Err(DomainError("type", path, "expected a list of non-empty strings"))
    return Ok(tuple(item.strip() for item in value))


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

    tolerance = raw.get("background_tolerance", 24)
    if not isinstance(tolerance, int) or not 0 <= tolerance <= 128:
        return Err(DomainError("value", "policy.background_tolerance", "must be an integer in [0, 128]"))
    cell = raw.get("halftone_cell", 8)
    if not isinstance(cell, int) or cell < 2 or cell > 64:
        return Err(DomainError("value", "policy.halftone_cell", "must be an integer in [2, 64]"))

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
        target_garments=values["target_garments"] or ProcessingPolicy.target_garments,
        edge_strategy=strategy,
        requested_variants=values["requested_variants"] or ProcessingPolicy.requested_variants,
        mode=mode,
        protected_regions=tuple(regions),
        background_tolerance=tolerance,
        halftone_cell=cell,
    ))
