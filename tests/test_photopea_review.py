from __future__ import annotations

from printify_artwork_cleaner.domain.models import MaskReviewDecision, PhotopeaCheckpoint, RasterMaskRevision
from printify_artwork_cleaner.domain.photopea_review import run_bounded_photopea_review


def _revision(parent: str, checkpoint: str, revision_id: str) -> RasterMaskRevision:
    return RasterMaskRevision(
        revision_id=revision_id,
        parent_revision_id=parent,
        source_sha256="a" * 64,
        checkpoint_sha256=checkpoint,
        base_mask_sha256="b" * 64,
        result_mask_sha256="c" * 64,
        confidence=0.95,
    )


def test_bounded_review_applies_raster_correction_then_accepts() -> None:
    first = PhotopeaCheckpoint("r1", "checkpoint-1", "a" * 64, "checkpoint-1", "mask-1", ("art-1",))
    second = PhotopeaCheckpoint("r2", "checkpoint-2", "a" * 64, "checkpoint-2", "mask-2", ("art-2",))
    calls = []

    def review(checkpoint):
        calls.append(checkpoint.revision_id)
        if checkpoint.revision_id == "r1":
            return MaskReviewDecision(False, "a" * 64, "checkpoint-1", _revision("r1", "checkpoint-1", "r2"))
        return MaskReviewDecision(True, "a" * 64, "checkpoint-2")

    result = run_bounded_photopea_review(first, review, lambda revision: second, lambda: 0.0)
    assert result.status == "accepted"
    assert result.revisions == 1
    assert result.checkpoint.revision_id == "r2"
    assert calls == ["r1", "r2"]


def test_review_rejects_stale_source_or_checkpoint() -> None:
    first = PhotopeaCheckpoint("r1", "checkpoint-1", "a" * 64, "checkpoint-1", "mask-1", "art-1")
    decision = lambda checkpoint: MaskReviewDecision(True, "f" * 64, "checkpoint-1")
    result = run_bounded_photopea_review(first, decision, lambda revision: first, lambda: 0.0)
    assert result.status == "review_required"
    assert result.reason == "vision_source_hash_mismatch"

    stale = lambda checkpoint: MaskReviewDecision(True, "a" * 64, "stale")
    result = run_bounded_photopea_review(first, stale, lambda revision: first, lambda: 0.0)
    assert result.reason == "vision_checkpoint_hash_mismatch"


def test_review_stops_at_revision_budget() -> None:
    first = PhotopeaCheckpoint("r1", "checkpoint-1", "a" * 64, "checkpoint-1", "mask-1", "art-1")
    next_checkpoint = PhotopeaCheckpoint("r2", "checkpoint-2", "a" * 64, "checkpoint-2", "mask-2", "art-2")
    decision = lambda checkpoint: MaskReviewDecision(False, "a" * 64, checkpoint.checkpoint_sha256, _revision(checkpoint.revision_id, checkpoint.checkpoint_sha256, "r2"))
    result = run_bounded_photopea_review(first, decision, lambda revision: next_checkpoint, lambda: 0.0, max_revisions=0)
    assert result.status == "review_required"
    assert result.reason == "photopea_revision_budget_exhausted"
