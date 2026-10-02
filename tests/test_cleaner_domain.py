from __future__ import annotations

import numpy as np

from printify_artwork_cleaner.domain.image_math import (
    binary_alpha,
    compose_alpha,
    edge_connected_background_mask,
    halftone_alpha,
    inspect_rgba,
    protected_mask,
    resize_rgba_premultiplied,
)
from printify_artwork_cleaner.domain.mask import create_mask_revision
from printify_artwork_cleaner.domain.models import EdgeStrategy, Err, ProcessingPolicy, freeze_policy


def test_policy_freeze_rejects_bad_enum_and_keeps_immutable_tuples() -> None:
    result = freeze_policy({"edge_strategy": "unknown"})
    assert isinstance(result, Err)
    accepted = freeze_policy({"must_keep": ["eyes"], "protected_regions": [{"x": 0, "y": 0, "width": 0.5, "height": 0.5}]})
    assert not isinstance(accepted, Err)
    assert accepted.value.must_keep == ("eyes",)
    assert accepted.value.edge_strategy is EdgeStrategy.AUTO_PRINT_SAFE


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
