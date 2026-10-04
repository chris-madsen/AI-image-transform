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
