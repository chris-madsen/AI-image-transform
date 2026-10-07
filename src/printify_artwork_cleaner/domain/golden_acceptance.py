from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


@dataclass(frozen=True, slots=True)
class GoldenRegion:
    """A pixel rectangle whose approved artwork must remain intact."""

    name: str
    left: int
    top: int
    right: int
    bottom: int

    def view(self, image: np.ndarray) -> np.ndarray:
        return image[self.top:self.bottom, self.left:self.right]


@dataclass(frozen=True, slots=True)
class GoldenAcceptance:
    """Pure acceptance result for a reviewed full-resolution reference."""

    passed: bool
    errors: tuple[str, ...]
    metrics: Mapping[str, int | float]


def _external_edge(alpha: np.ndarray) -> np.ndarray:
    foreground = np.asarray(alpha, dtype=np.uint8) > 0
    padded = np.pad(foreground, 1, constant_values=False)
    adjacent_background = (
        ~padded[:-2, 1:-1]
        | ~padded[2:, 1:-1]
        | ~padded[1:-1, :-2]
        | ~padded[1:-1, 2:]
    )
    return foreground & adjacent_background


def evaluate_golden_render(
    candidate: np.ndarray,
    approved: np.ndarray,
    regions: tuple[GoldenRegion, ...],
    *,
    protected_rgb_max_delta: int = 0,
    protected_alpha_loss_pixels: int = 0,
    lower_fade_alpha_mae: float = 0.0,
    external_edge_alpha_loss_pixels: int = 0,
) -> GoldenAcceptance:
    """Compare a candidate render with the approved raster without doing I/O.

    The checks intentionally target the failure modes that generic fragmentation
    scores miss: missing semantic details, altered eyes/whiskers, a damaged lower
    fade, and a broken external perimeter.  A caller may choose non-zero
    tolerances for a separately approved print profile; the Panther fixture uses
    zero tolerances because its PSD render is the owner-approved reference.
    """

    candidate = np.asarray(candidate, dtype=np.uint8)
    approved = np.asarray(approved, dtype=np.uint8)
    errors: list[str] = []
    metrics: dict[str, int | float] = {}
    if candidate.shape != approved.shape or candidate.ndim != 3 or candidate.shape[-1] != 4:
        return GoldenAcceptance(False, ("candidate dimensions or RGBA channels differ from approved render",), metrics)

    approved_alpha = approved[..., 3]
    candidate_alpha = candidate[..., 3]
    edge = _external_edge(approved_alpha)
    edge_loss = int(np.count_nonzero(edge & (candidate_alpha == 0)))
    metrics["external_edge_alpha_loss_pixels"] = edge_loss
    if edge_loss > external_edge_alpha_loss_pixels:
        errors.append("external edge continuity is broken")

    for region in regions:
        expected = region.view(approved)
        actual = region.view(candidate)
        expected_foreground = expected[..., 3] > 0
        alpha_loss = int(np.count_nonzero(expected_foreground & (actual[..., 3] == 0)))
        rgb_delta = np.abs(actual[..., :3].astype(np.int16) - expected[..., :3].astype(np.int16))
        protected_rgb_delta = int(np.count_nonzero(np.any(rgb_delta > protected_rgb_max_delta, axis=-1) & expected_foreground))
        metrics[f"{region.name}_alpha_loss_pixels"] = alpha_loss
        metrics[f"{region.name}_rgb_diff_pixels"] = protected_rgb_delta
        if alpha_loss > protected_alpha_loss_pixels:
            errors.append(f"protected region lost pixels: {region.name}")
        if protected_rgb_delta:
            errors.append(f"protected region RGB changed: {region.name}")

        if region.name == "lower_fade":
            fade_mae = float(np.abs(actual[..., 3].astype(np.int16) - expected[..., 3].astype(np.int16)).mean())
            metrics["lower_fade_alpha_mae"] = fade_mae
            if fade_mae > lower_fade_alpha_mae:
                errors.append("lower fade differs from approved alpha profile")

    return GoldenAcceptance(not errors, tuple(errors), metrics)
