from __future__ import annotations

from collections.abc import Callable

from .models import MaskReviewDecision, PhotopeaCheckpoint, PhotopeaReviewOutcome, RasterMaskRevision


ReviewCheckpoint = Callable[[PhotopeaCheckpoint], MaskReviewDecision | None]
ApplyRevision = Callable[[RasterMaskRevision], PhotopeaCheckpoint]


def run_bounded_photopea_review(
    initial: PhotopeaCheckpoint,
    review: ReviewCheckpoint,
    apply_revision: ApplyRevision,
    now: Callable[[], float],
    *,
    max_revisions: int = 3,
    budget_seconds: float = 300.0,
) -> PhotopeaReviewOutcome:
    """Run a fail-closed checkpoint/review/correction loop.

    The function is deterministic for injected callbacks and clock. It never
    interprets natural language and never accepts executable Photopea code.
    Every correction must be chained to the current checkpoint and source.
    """

    if max_revisions < 0 or budget_seconds <= 0:
        return PhotopeaReviewOutcome("review_required", initial, 0, "invalid review budget")
    started = now()
    current = initial
    revisions = 0
    while True:
        if now() - started > budget_seconds:
            return PhotopeaReviewOutcome("review_required", current, revisions, "photopea_review_budget_exhausted")
        decision = review(current)
        if decision is None:
            return PhotopeaReviewOutcome("review_required", current, revisions, "vision_decision_missing")
        if decision.source_sha256 != current.source_sha256:
            return PhotopeaReviewOutcome("review_required", current, revisions, "vision_source_hash_mismatch")
        if decision.checkpoint_sha256 != current.checkpoint_sha256:
            return PhotopeaReviewOutcome("review_required", current, revisions, "vision_checkpoint_hash_mismatch")
        if decision.accepted:
            return PhotopeaReviewOutcome("accepted", current, revisions)
        if decision.revision is None:
            return PhotopeaReviewOutcome("review_required", current, revisions, "vision_correction_missing")
        if revisions >= max_revisions:
            return PhotopeaReviewOutcome("review_required", current, revisions, "photopea_revision_budget_exhausted")
        revision = decision.revision
        if revision.source_sha256 != current.source_sha256:
            return PhotopeaReviewOutcome("review_required", current, revisions, "revision_source_hash_mismatch")
        if revision.parent_revision_id != current.revision_id:
            return PhotopeaReviewOutcome("review_required", current, revisions, "revision_parent_mismatch")
        if revision.checkpoint_sha256 != current.checkpoint_sha256:
            return PhotopeaReviewOutcome("review_required", current, revisions, "revision_checkpoint_mismatch")
        next_checkpoint = apply_revision(revision)
        if next_checkpoint.source_sha256 != current.source_sha256 or next_checkpoint.revision_id != revision.revision_id:
            return PhotopeaReviewOutcome("review_required", current, revisions, "photopea_checkpoint_binding_mismatch")
        current = next_checkpoint
        revisions += 1
