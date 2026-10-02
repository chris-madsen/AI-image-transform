from __future__ import annotations

import numpy as np

from .models import ArtworkInspection, JobStatus, ProcessingPolicy, ValidationResult


def _frame_score(alpha: np.ndarray) -> float:
    border = np.concatenate((alpha[0], alpha[-1], alpha[1:-1, 0], alpha[1:-1, -1]))
    return float(np.mean(border > 8))


def _halo_score(rgba: np.ndarray) -> float:
    alpha = rgba[..., 3]
    partial = alpha[(alpha > 0) & (alpha < 255)]
    if partial.size == 0:
        return 0.0
    return float(np.mean(partial < 96))


def validate_candidate(
    rgba: np.ndarray,
    source: np.ndarray,
    inspection: ArtworkInspection,
    policy: ProcessingPolicy,
    protected: np.ndarray,
) -> ValidationResult:
    result = np.asarray(rgba, dtype=np.uint8)
    original = np.asarray(source, dtype=np.uint8)
    alpha = result[..., 3]
    visible_changed = np.any(result[..., :3] != original[..., :3], axis=-1) & (result[..., 3] > 0)
    changed_pixels = int(np.count_nonzero(visible_changed))
    protected_score = 1.0
    if np.any(protected):
        protected_score = float(np.mean(alpha[protected] >= original[..., 3][protected]))
    halo = _halo_score(result)
    frame = _frame_score(alpha)
    warnings: list[str] = []
    review: list[str] = []
    if changed_pixels:
        warnings.append("visible RGB changed")
    if inspection.crop_risk:
        review.append("crop_risk")
    if protected_score < 1.0:
        review.append("protected_detail_loss")
    if frame > 0.25:
        warnings.append("possible_frame")
        review.append("frame")
    if halo > 0.35 and policy.edge_strategy.value in {"auto_print_safe", "controlled_soft_alpha"}:
        warnings.append("partial_alpha_may_create_dark_garment_glow")
        review.append("halo")
    status = JobStatus.PASSED
    if review:
        status = JobStatus.REVIEW_REQUIRED
    if inspection.classification == "ambiguous_boundary_contact" and not policy.protected_regions:
        status = JobStatus.REFUSED
        review.append("ambiguous_boundary_contact")
    return ValidationResult(status, halo, frame, protected_score, changed_pixels, tuple(warnings), tuple(dict.fromkeys(review)))
