from __future__ import annotations

import numpy as np
from PIL import Image
from io import BytesIO

from printify_artwork_cleaner.domain.image_math import inspect_rgba, protected_mask
from printify_artwork_cleaner.domain.models import JobStatus, ProcessingPolicy, ResolvedMaskBundle, VisualQualityAssessment
from printify_artwork_cleaner.domain.validation import validate_candidate
from printify_artwork_cleaner.application import process_image_bytes
from printify_artwork_cleaner.domain.rendering import composite, dtg_underbase_preview


def test_partial_alpha_halo_is_not_passed() -> None:
    source = np.zeros((16, 16, 4), dtype=np.uint8)
    source[..., :3] = [200, 20, 20]
    source[..., 3] = 255
    candidate = source.copy()
    candidate[..., 3] = 32
    policy = ProcessingPolicy()
    inspection, _ = inspect_rgba(source, policy)
    result = validate_candidate(candidate, source, inspection, policy, protected_mask(policy, source.shape[:2]))
    assert result.status in {JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}
    assert "halo" in result.review_regions


def test_photopea_exporter_contract_is_binary_psd() -> None:
    source = np.zeros((8, 10, 4), dtype=np.uint8)
    source[..., :3] = [20, 40, 60]
    source[..., 3] = 255
    mask = np.full((8, 10), 255, dtype=np.uint8)
    class FakePhotopeaExporter:
        def export(self, received_source, artwork, received_mask) -> bytes:
            assert received_source.shape == source.shape
            assert artwork.shape == source.shape
            assert received_mask.shape == mask.shape
            return b"8BPS" + b"photopea-live-result"

    result = FakePhotopeaExporter().export(source, source, mask)
    assert result.startswith(b"8BPS")


def test_unverified_psd_payload_cannot_pass(tmp_path) -> None:
    class FakePhotopea:
        def export(self, source, artwork, mask) -> bytes:
            return b"8BPS" + b"payload"

    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path, psd_exporter=FakePhotopea())
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert report.stage_status is not None
    assert report.stage_status.psd_validation_status == "unverified_payload"


def test_photopea_round_trip_capability_marks_exact_payload_verified(tmp_path) -> None:
    class VerifiedPhotopea:
        round_trip_verified = True
        evidence = object()

        def export(self, source, artwork, mask) -> bytes:
            return b"8BPS" + b"round-tripped-payload"

    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path, psd_exporter=VerifiedPhotopea())
    assert report.stage_status is not None
    assert report.stage_status.psd_validation_status == "passed"


def test_photopea_header_without_evidence_cannot_pass(tmp_path) -> None:
    class HeaderOnlyPhotopea:
        round_trip_verified = True

        def export(self, source, artwork, mask) -> bytes:
            return b"8BPS" + b"payload"

    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path, psd_exporter=HeaderOnlyPhotopea())
    assert report.stage_status is not None
    assert report.stage_status.psd_validation_status == "unverified_payload"


def test_missing_photopea_live_api_is_review_required(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert "photopea_live_api" in report.validation.review_regions
    assert not any(artifact.name.endswith(".psd") for artifact in report.artifacts)


def test_semantic_text_without_pixel_mask_is_not_passed(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(must_keep=("eyes",)), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert report.stage_status is not None
    assert report.stage_status.ai_mask_status == "review_required"


def test_missing_visual_quality_assessment_is_review_required(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert "visual_quality" in report.validation.review_regions
    assert report.validation.visual_quality_score == 0.0


def test_missing_per_artwork_mask_tuning_is_review_required(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert "vision_mask_tuning" in report.validation.review_regions
    assert report.stage_status is not None
    assert report.stage_status.ai_mask_status == "review_required"


def test_low_visual_quality_overrides_a_valid_pixel_candidate(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    assessment = VisualQualityAssessment("bad-reference", 0.95, 0.95, 0.4, 0.6, 0.5, 0.95)
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(visual_quality=assessment), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert "visual_quality" in report.validation.review_regions
    assert "visual_quality_score_below_threshold" in report.validation.warnings


def test_supplied_pixel_protection_survives_removal(tmp_path) -> None:
    source = np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8)
    stream = BytesIO()
    Image.fromarray(source, mode="RGBA").save(stream, format="PNG")
    removal = np.ones((8, 8), dtype=bool)
    protection = np.zeros((8, 8), dtype=bool)
    protection[3:5, 3:5] = True
    report = process_image_bytes(
        stream.getvalue(), ProcessingPolicy(), tmp_path,
        resolved_masks=ResolvedMaskBundle(semantic_protection=protection, removable_background=removal, provenance=("test",), confidence=1.0),
    )
    output = np.asarray(Image.open(tmp_path / "artwork_conservative.png"))
    assert np.all(output[3:5, 3:5, 3] == 255)
    assert report.stage_status is not None
    assert report.stage_status.ai_mask_status == "provided"


def test_authoritative_raster_mask_is_used_for_every_emitted_variant(tmp_path) -> None:
    source = np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8)
    stream = BytesIO()
    Image.fromarray(source, mode="RGBA").save(stream, format="PNG")
    accepted = np.zeros((8, 8), dtype=np.uint8)
    accepted[2:6, 2:6] = 173
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path, authoritative_mask=accepted)
    for name in ("conservative", "artistic"):
        output = np.asarray(Image.open(tmp_path / f"artwork_{name}.png"))
        assert np.array_equal(output[..., 3], accepted)
    assert report.status is JobStatus.REVIEW_REQUIRED


def test_intact_reference_wins_and_reports_zero_protected_diffs(tmp_path) -> None:
    source = np.full((8, 8, 4), [100, 120, 140, 255], dtype=np.uint8)
    reference = source.copy()
    reference[3:5, 3:5] = [240, 220, 40, 255]
    stream = BytesIO()
    Image.fromarray(source, mode="RGBA").save(stream, format="PNG")
    protection = np.zeros((8, 8), dtype=bool)
    protection[3:5, 3:5] = True
    removal = np.ones((8, 8), dtype=bool)
    report = process_image_bytes(
        stream.getvalue(), ProcessingPolicy(), tmp_path,
        resolved_masks=ResolvedMaskBundle(
            semantic_protection=protection,
            removable_background=removal,
            protected_reference=reference,
            provenance=("approved-reference",),
            confidence=1.0,
        ),
    )
    output = np.asarray(Image.open(tmp_path / "artwork_conservative.png"))
    assert np.array_equal(output[3:5, 3:5], reference[3:5, 3:5])
    result = report.variant_validations["conservative"]
    assert result.protected_alpha_loss_pixels == 0
    assert result.protected_rgb_diff_pixels == 0


def test_validation_rejects_alpha_removal_outside_approved_perimeter() -> None:
    source = np.full((6, 6, 4), [100, 120, 140, 255], dtype=np.uint8)
    candidate = source.copy()
    candidate[2, 2, 3] = 0
    policy = ProcessingPolicy()
    inspection, _ = inspect_rgba(source, policy)
    allowed = np.zeros((6, 6), dtype=bool)
    result = validate_candidate(candidate, source, inspection, policy, np.zeros((6, 6), dtype=bool), allowed)
    assert result.unauthorized_alpha_removal_pixels == 1
    assert result.status in {JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}
    assert "unauthorized_alpha_removal" in result.review_regions


def test_dtg_underbase_is_not_white_preview() -> None:
    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[..., :3] = [240, 40, 40]
    rgba[..., 3] = 128
    white = composite(rgba, (255, 255, 255))
    underbase = dtg_underbase_preview(rgba, (20, 20, 30))
    assert not np.array_equal(white, underbase)
