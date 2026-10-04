from __future__ import annotations

import numpy as np

from .models import ArtworkInspection, JobStatus, ProcessingPolicy, ValidationResult
from .visual_quality import evaluate_visual_quality


def _frame_score(alpha: np.ndarray) -> float:
    border = np.concatenate((alpha[0], alpha[-1], alpha[1:-1, 0], alpha[1:-1, -1]))
    return float(np.mean(border > 8))


def _halo_score(rgba: np.ndarray) -> float:
    alpha = rgba[..., 3]
    low_alpha = (alpha > 0) & (alpha < 96)
    if not np.any(low_alpha):
        return 0.0
    # A narrow intentional fade is not a broad glow. Measure low-alpha pixels
    # against the complete canvas, rather than against the partial-alpha subset
    # (where every controlled fade would otherwise score 1.0).
    return float(np.mean(low_alpha))


def validate_candidate(
    rgba: np.ndarray,
    source: np.ndarray,
    inspection: ArtworkInspection,
    policy: ProcessingPolicy,
    protected: np.ndarray,
    allowed_removal: np.ndarray | None = None,
) -> ValidationResult:
    result = np.asarray(rgba, dtype=np.uint8)
    original = np.asarray(source, dtype=np.uint8)
    alpha = result[..., 3]
    visible_changed = np.any(result[..., :3] != original[..., :3], axis=-1) & (result[..., 3] > 0)
    changed_pixels = int(np.count_nonzero(visible_changed))
    protected_score = 1.0
    protected_alpha_loss_pixels = 0
    protected_rgb_diff_pixels = 0
    unauthorized_alpha_removal_pixels = 0
    if np.any(protected):
        protected_alpha_loss_pixels = int(np.count_nonzero(alpha[protected] < original[..., 3][protected]))
        protected_rgb_diff_pixels = int(np.count_nonzero(np.any(result[..., :3][protected] != original[..., :3][protected], axis=-1)))
        protected_score = float(np.mean(alpha[protected] >= original[..., 3][protected]))
    if allowed_removal is not None:
        unauthorized_alpha_removal_pixels = int(np.count_nonzero((alpha < original[..., 3]) & ~np.asarray(allowed_removal, dtype=bool)))
    halo = _halo_score(result)
    frame = _frame_score(alpha)
    warnings: list[str] = []
    review: list[str] = []
    if changed_pixels:
        warnings.append("visible RGB changed")
    if inspection.crop_risk:
        review.append("crop_risk")
    if protected_alpha_loss_pixels or protected_rgb_diff_pixels:
        review.append("protected_detail_loss")
    if unauthorized_alpha_removal_pixels:
        warnings.append("alpha_removed_outside_approved_perimeter")
        review.append("unauthorized_alpha_removal")
    if frame > 0.25:
        warnings.append("possible_frame")
        review.append("frame")
    if halo > 0.08 and policy.edge_strategy.value in {"auto_print_safe", "controlled_soft_alpha"}:
        warnings.append("partial_alpha_may_create_dark_garment_glow")
        review.append("halo")
    status = JobStatus.PASSED
    if review:
        status = JobStatus.REVIEW_REQUIRED
    if inspection.classification == "ambiguous_boundary_contact" and not policy.protected_regions:
        status = JobStatus.REFUSED
        review.append("ambiguous_boundary_contact")
    visual_quality = evaluate_visual_quality(result, policy.visual_quality)
    warnings.extend(visual_quality.warnings)
    review.extend(visual_quality.review_regions)
    if visual_quality.review_regions:
        status = JobStatus.REVIEW_REQUIRED
    return ValidationResult(
        status,
        halo,
        frame,
        protected_score,
        changed_pixels,
        protected_alpha_loss_pixels,
        protected_rgb_diff_pixels,
        unauthorized_alpha_removal_pixels,
        tuple(warnings),
        tuple(dict.fromkeys(review)),
        visual_quality.score,
        visual_quality.fragmentation_score,
        visual_quality.confidence,
    )
