from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import VisualQualityAssessment


MINIMUM_SCORE = 0.78
MINIMUM_CONFIDENCE = 0.75


@dataclass(frozen=True, slots=True)
class VisualQualityResult:
    score: float
    fragmentation_score: float
    confidence: float
    warnings: tuple[str, ...]
    review_regions: tuple[str, ...]
    edge_chroma_contamination: float = 0.0
    contour_distance_score: float = 1.0
    dark_garment_halo_score: float = 0.0


def _edge_fragmentation_score(alpha: np.ndarray) -> float:
    foreground = np.asarray(alpha, dtype=np.uint8) > 8
    foreground_pixels = int(np.count_nonzero(foreground))
    if foreground_pixels == 0:
        return 0.0
    padded = np.pad(foreground, 1, mode="constant", constant_values=False)
    neighbours = sum(
        padded[dy:dy + foreground.shape[0], dx:dx + foreground.shape[1]]
        for dy in (0, 1, 2)
        for dx in (0, 1, 2)
        if (dy, dx) != (1, 1)
    )
    isolated_ratio = float(np.count_nonzero(foreground & (neighbours <= 1))) / foreground_pixels
    return float(np.clip(1.0 - isolated_ratio * 6.0, 0.0, 1.0))


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    value = np.asarray(mask, dtype=bool)
    padded = np.pad(value, radius, mode="constant", constant_values=False)
    height, width = value.shape
    return np.logical_or.reduce(
        [
            padded[top:top + height, left:left + width]
            for top in range(radius * 2 + 1)
            for left in range(radius * 2 + 1)
        ]
    )


def _edge_quality_metrics(rgba: np.ndarray, source: np.ndarray | None = None) -> tuple[float, float, float]:
    """Measure fringe contamination without pretending to understand semantics.

    The metrics are deliberately conservative safety signals. They do not
    replace the semantic reviewer or the approved golden reference; they make
    broad low-alpha veils and removed-background colour leaking into a fringe
    visible to the validation boundary.
    """
    result = np.asarray(rgba, dtype=np.uint8)
    alpha = result[..., 3]
    partial = (alpha > 0) & (alpha < 160)
    if not np.any(partial):
        return 0.0, 1.0, 0.0

    opaque = alpha >= 240
    contour = _dilate(opaque, 3)
    outside_contour = partial & ~contour
    contour_distance_score = float(1.0 - np.mean(outside_contour[partial]))

    dark_rgb = result[..., :3].astype(np.float32) * (alpha[..., None].astype(np.float32) / 255.0)
    dark_garment_halo_score = float(np.mean(np.max(dark_rgb[partial], axis=1)) / 255.0)

    chroma_contamination = 0.0
    if source is not None:
        original = np.asarray(source, dtype=np.uint8)
        removed = (original[..., 3] > 0) & (alpha == 0)
        if np.any(removed):
            background = np.median(original[..., :3][removed], axis=0).astype(np.float32)
            distance = np.max(np.abs(result[..., :3].astype(np.float32) - background), axis=-1)
            chroma_contamination = float(np.mean((distance <= 28)[partial]))
    return chroma_contamination, contour_distance_score, dark_garment_halo_score


def evaluate_visual_quality(
    rgba: np.ndarray,
    assessment: VisualQualityAssessment | None,
) -> VisualQualityResult:
    """Combine agent judgement with deterministic anti-noise safety checks.

    The service never invents an aesthetic judgement. The agent/vision boundary
    must provide one, while this function prevents a high claimed score from
    approving an obviously fragmented alpha edge.
    """

    if assessment is None:
        return VisualQualityResult(0.0, 0.0, 0.0, ("visual_quality_assessment_missing",), ("visual_quality",))
    fragmentation = _edge_fragmentation_score(np.asarray(rgba, dtype=np.uint8)[..., 3])
    model_score = min(
        assessment.overall_score,
        assessment.subject_integrity,
        assessment.intentional_detail_score,
        assessment.edge_naturalness,
        assessment.artifact_free_score,
    )
    score = min(model_score, fragmentation)
    warnings: list[str] = []
    review: list[str] = []
    if assessment.confidence < MINIMUM_CONFIDENCE:
        warnings.append("visual_quality_confidence_below_threshold")
        review.append("visual_quality_confidence")
    if model_score < MINIMUM_SCORE:
        warnings.append("visual_quality_score_below_threshold")
        review.append("visual_quality")
    if fragmentation < MINIMUM_SCORE:
        warnings.append("alpha_edge_is_fragmented_or_noisy")
        review.append("edge_aesthetics")
    return VisualQualityResult(score, fragmentation, assessment.confidence, tuple(warnings), tuple(dict.fromkeys(review)))
