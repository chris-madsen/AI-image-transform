from __future__ import annotations

import numpy as np

from printify_artwork_cleaner.domain.image_math import (
    binary_alpha,
    compose_alpha,
    compose_artistic_perimeter_alpha,
    edge_connected_background_mask,
    halftone_alpha,
    inspect_rgba,
    protected_mask,
    resize_rgba_premultiplied,
)
from printify_artwork_cleaner.domain.mask import create_mask_revision
from printify_artwork_cleaner.domain.models import EdgeStrategy, Err, ProcessingPolicy, freeze_policy
from printify_artwork_cleaner.domain.rendering import apply_variant
from printify_artwork_cleaner.domain.validation import _halo_score


def test_policy_freeze_rejects_bad_enum_and_keeps_immutable_tuples() -> None:
    result = freeze_policy({"edge_strategy": "unknown"})
    assert isinstance(result, Err)
    accepted = freeze_policy({"must_keep": ["eyes"], "protected_regions": [{"x": 0, "y": 0, "width": 0.5, "height": 0.5}]})
    assert not isinstance(accepted, Err)
    assert accepted.value.must_keep == ("eyes",)
    assert accepted.value.edge_strategy is EdgeStrategy.AUTO_PRINT_SAFE


def test_policy_freezes_visual_quality_assessment() -> None:
    result = freeze_policy({
        "visual_quality": {
            "reference_id": "panther-v1",
            "source_sha256": "a" * 64,
            "checkpoint_sha256": "b" * 64,
            "overall_score": 0.9,
            "subject_integrity": 0.95,
            "intentional_detail_score": 0.88,
            "edge_naturalness": 0.86,
            "artifact_free_score": 0.92,
            "confidence": 0.9,
        }
    }, allow_runtime_evidence=True)
    assert not isinstance(result, Err)
    assert result.value.visual_quality is not None
    assert result.value.visual_quality.reference_id == "panther-v1"
    assert isinstance(result.value.visual_quality.reviewer_notes, tuple)


def test_policy_freezes_per_artwork_mask_tuning() -> None:
    result = freeze_policy({
        "mask_tuning": {
            "decision_id": "source-abc-r2",
            "source_sha256": "a" * 64,
            "background_tolerance": 11,
            "fade_low_distance": 3,
            "fade_full_distance": 72,
            "fade_band_radius": 6,
            "confidence": 0.87,
        },
    }, allow_runtime_evidence=True)
    assert not isinstance(result, Err)
    assert result.value.mask_tuning is not None
    assert result.value.effective_background_tolerance == 11


def test_policy_rejects_invalid_mask_tuning() -> None:
    result = freeze_policy({"mask_tuning": {"decision_id": "bad", "confidence": 0.5}})
    assert isinstance(result, Err)


def test_public_policy_rejects_photopea_revision_evidence() -> None:
    result = freeze_policy({"photopea_mask_revision": {"revision_id": "vision-r1"}})
    assert isinstance(result, Err)
    assert result.error.code == "forbidden"


def test_policy_rejects_legacy_polygon_photopea_plan() -> None:
    result = freeze_policy({
        "photopea_mask_plan": {
            "revision_id": "bad",
            "subject_polygons": [[[0, 0], [2, 0], [0, 1]]],
            "confidence": 1,
        },
    })
    assert isinstance(result, Err)
    assert result.error.code == "deprecated"


def test_policy_rejects_unbounded_visual_quality_score() -> None:
    result = freeze_policy({"visual_quality": {"overall_score": 1.2}})
    assert isinstance(result, Err)


def test_edge_connected_background_does_not_remove_internal_same_color() -> None:
    rgba = np.zeros((7, 7, 4), dtype=np.uint8)
    rgba[..., :3] = [10, 20, 30]
    rgba[..., 3] = 255
    rgba[1:6, 1:6, :3] = [100, 110, 120]
    rgba[2:5, 2:5, :3] = [10, 20, 30]
    mask = edge_connected_background_mask(rgba, 2)
    assert mask[0, 0]
    assert not mask[3, 3]


def test_protected_region_survives_background_mask() -> None:
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[..., :3] = [200, 200, 200]
    rgba[..., 3] = 255
    policy = ProcessingPolicy(protected_regions=(freeze_policy({"protected_regions": [{"x": 0, "y": 0, "width": 0.5, "height": 0.5}]}).value.protected_regions[0],))
    inspection, background = inspect_rgba(rgba, policy)
    result = compose_alpha(rgba[..., 3], background, protected_mask(policy, rgba.shape[:2]))
    assert inspection.classification == "ambiguous_boundary_contact"
    assert result[1, 1] == 255


def test_artistic_perimeter_preserves_fade_but_not_flat_background() -> None:
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[..., :3] = [70, 100, 120]
    rgba[..., 3] = 255
    rgba[2:6, 2:6, :3] = [20, 20, 20]
    rgba[1, 3, :3] = [64, 94, 114]
    removable = np.ones((8, 8), dtype=bool)
    removable[2:6, 2:6] = False
    alpha = compose_artistic_perimeter_alpha(rgba, rgba[..., 3], removable, np.zeros((8, 8), dtype=bool))
    assert alpha[0, 0] == 0
    assert 0 < alpha[1, 3] < 255
    assert alpha[3, 3] == 255


def test_artistic_variant_keeps_partial_alpha() -> None:
    source = np.zeros((2, 2, 4), dtype=np.uint8)
    source[..., :3] = 120
    source[..., 3] = np.array([[0, 96], [192, 255]], dtype=np.uint8)
    policy = ProcessingPolicy(requested_variants=("artistic",))

    rendered = apply_variant(source, "artistic", policy)

    assert rendered[..., 3].tolist() == [[0, 96], [192, 255]]


def test_print_safe_strategy_cannot_be_bypassed_by_artistic_variant() -> None:
    source = np.zeros((8, 8, 4), dtype=np.uint8)
    source[..., :3] = 120
    source[..., 3] = np.arange(64, dtype=np.uint8).reshape(8, 8) * 4

    rendered = apply_variant(
        source,
        "artistic",
        ProcessingPolicy(edge_strategy=EdgeStrategy.HALFTONE, halftone_cell=4),
    )

    assert set(np.unique(rendered[..., 3])) <= {0, 255}


def test_binary_and_controlled_soft_strategies_override_named_variant() -> None:
    source = np.zeros((1, 3, 4), dtype=np.uint8)
    source[..., :3] = 120
    source[..., 3] = [64, 128, 255]

    binary = apply_variant(source, "artistic", ProcessingPolicy(edge_strategy=EdgeStrategy.BINARY_ALPHA))
    soft = apply_variant(source, "conservative", ProcessingPolicy(edge_strategy=EdgeStrategy.CONTROLLED_SOFT_ALPHA))

    assert binary[..., 3].tolist() == [[0, 255, 255]]
    assert soft[..., 3].tolist() == [[80, 160, 255]]


def test_halo_score_is_canvas_area_not_partial_area() -> None:
    rgba = np.zeros((10, 10, 4), dtype=np.uint8)
    rgba[:2, :, 3] = 32

    assert _halo_score(rgba) == 0.2


def test_resize_and_halftone_are_safe() -> None:
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[..., :3] = [255, 255, 0]
    rgba[1:3, 1:3, 3] = 255
    resized = resize_rgba_premultiplied(rgba, (8, 8))
    assert np.all(resized[..., 3][resized[..., 3] == 0] == 0)
    screened = halftone_alpha(np.full((16, 16), 128, dtype=np.uint8), 8)
    assert set(np.unique(screened)) == {0, 255}
    assert set(np.unique(binary_alpha(np.array([[0, 128, 255]], dtype=np.uint8)))) == {0, 255}


def test_inspection_flags_ambiguous_edge_contact() -> None:
    rgba = np.full((5, 5, 4), 255, dtype=np.uint8)
    rgba[..., :3] = [0, 0, 0]
    policy = ProcessingPolicy(background_tolerance=0)
    inspection, _ = inspect_rgba(rgba, policy)
    assert inspection.crop_risk is True
    assert inspection.classification == "ambiguous_boundary_contact"


def test_mask_revision_is_immutable_and_chained() -> None:
    first = create_mask_revision(np.zeros((4, 4), dtype=np.uint8), operations=("edge_remove",))
    second = create_mask_revision(np.ones((4, 4), dtype=np.uint8) * 255, parent=first, operations=("manual_restore",))
    assert second.parent_id == first.revision_id
    assert second.mask_sha256 != first.mask_sha256
    assert second.operations == ("manual_restore",)


def test_policy_rejects_unknown_variant_and_halftone_cell_changes_screen() -> None:
    assert isinstance(freeze_policy({"requested_variants": ["../../../escaped"]}), Err)
    alpha = np.full((32, 32), 128, dtype=np.uint8)
    assert not np.array_equal(halftone_alpha(alpha, 4), halftone_alpha(alpha, 16))


def test_canvas_policy_is_validated_and_preserves_aspect_ratio(tmp_path) -> None:
    from io import BytesIO
    from PIL import Image
    from printify_artwork_cleaner.application import process_image_bytes

    source = np.zeros((8, 16, 4), dtype=np.uint8)
    source[..., :3] = [200, 20, 20]
    source[..., 3] = 255
    stream = BytesIO()
    Image.fromarray(source, mode="RGBA").save(stream, format="PNG")
    policy = freeze_policy({"canvas_width": 32, "canvas_height": 32}).value
    report = process_image_bytes(stream.getvalue(), policy, tmp_path)
    output = Image.open(tmp_path / "artwork_conservative.png")
    assert output.size == (32, 32)
    assert report.inspection.source_sha256
    assert report.inspection.canonical_pixels_sha256
