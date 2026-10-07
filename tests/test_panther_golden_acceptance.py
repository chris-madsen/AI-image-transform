from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from printify_artwork_cleaner.domain.golden_acceptance import GoldenRegion, evaluate_golden_render


FIXTURE = Path(__file__).parent / "fixtures" / "panther_golden"


@pytest.fixture(scope="module")
def golden() -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    source_path = FIXTURE / str(manifest["source_file"])
    approved_path = FIXTURE / str(manifest["approved_render_file"])
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == manifest["source_sha256"]
    source = np.asarray(Image.open(source_path).convert("RGBA"))
    approved = np.asarray(Image.open(approved_path).convert("RGBA"))
    expected_alpha = np.asarray(Image.open(FIXTURE / str(manifest["approved_alpha_file"])).convert("L"))
    assert np.array_equal(approved[..., 3], expected_alpha)
    assert tuple(approved.shape[:2][::-1]) == tuple(manifest["dimensions"])
    return source, approved, manifest


def _regions(manifest: dict[str, object]) -> tuple[GoldenRegion, ...]:
    raw = manifest["regions"]
    assert isinstance(raw, dict)
    return tuple(GoldenRegion(name, *map(int, bounds)) for name, bounds in raw.items())


def _evaluate(candidate: np.ndarray, approved: np.ndarray, manifest: dict[str, object]):
    tolerances = manifest["tolerances"]
    assert isinstance(tolerances, dict)
    return evaluate_golden_render(
        candidate,
        approved,
        _regions(manifest),
        protected_rgb_max_delta=int(tolerances["protected_region_rgb_max_delta"]),
        protected_alpha_loss_pixels=int(tolerances["protected_region_alpha_loss_pixels"]),
        lower_fade_alpha_mae=float(tolerances["lower_fade_alpha_mae"]),
        external_edge_alpha_loss_pixels=int(tolerances["external_edge_alpha_loss_pixels"]),
    )


def test_approved_full_resolution_panther_reference_passes(golden) -> None:
    source, approved, manifest = golden
    assert source.shape == approved.shape == (5400, 4500, 4)
    result = _evaluate(approved, approved, manifest)
    assert result.passed, result.errors
    assert result.metrics["external_edge_alpha_loss_pixels"] == 0


@pytest.mark.parametrize("region_name", ["left_ear", "right_ear", "whiskers", "head_foliage"])
def test_panther_golden_rejects_lost_semantic_region(golden, region_name: str) -> None:
    _, approved, manifest = golden
    candidate = approved.copy()
    region = next(region for region in _regions(manifest) if region.name == region_name)
    candidate[region.top:region.bottom, region.left:region.right, 3] = 0
    result = _evaluate(candidate, approved, manifest)
    assert not result.passed
    assert any(region_name in error or "external edge" in error for error in result.errors)


def test_panther_golden_rejects_changed_eyes(golden) -> None:
    _, approved, manifest = golden
    candidate = approved.copy()
    region = next(region for region in _regions(manifest) if region.name == "eyes")
    candidate[region.top:region.bottom, region.left:region.right, :3] = 0
    result = _evaluate(candidate, approved, manifest)
    assert not result.passed
    assert "protected region RGB changed: eyes" in result.errors


def test_panther_golden_rejects_damaged_lower_fade(golden) -> None:
    _, approved, manifest = golden
    candidate = approved.copy()
    region = next(region for region in _regions(manifest) if region.name == "lower_fade")
    candidate[region.top:region.bottom, region.left:region.right, 3] = 255
    result = _evaluate(candidate, approved, manifest)
    assert not result.passed
    assert "lower fade differs from approved alpha profile" in result.errors


def test_panther_golden_rejects_broken_external_edge(golden) -> None:
    _, approved, manifest = golden
    candidate = approved.copy()
    alpha = approved[..., 3]
    edge = np.pad(alpha > 0, 1, constant_values=False)
    boundary = (alpha > 0) & (
        ~edge[:-2, 1:-1] | ~edge[2:, 1:-1] | ~edge[1:-1, :-2] | ~edge[1:-1, 2:]
    )
    y, x = np.argwhere(boundary)[0]
    candidate[y, x, 3] = 0
    result = _evaluate(candidate, approved, manifest)
    assert not result.passed
    assert "external edge continuity is broken" in result.errors
