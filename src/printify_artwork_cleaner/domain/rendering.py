from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .image_math import binary_alpha, canonicalize_hidden_rgb, halftone_alpha, resize_rgba_premultiplied
from .models import EdgeStrategy, ProcessingMode, ProcessingPolicy, VariantName


BACKGROUNDS: Mapping[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (119, 119, 119),
    "navy": (54, 75, 99),
    "blue_jean": (110, 142, 174),
}


@dataclass(frozen=True, slots=True)
class RenderPlan:
    mode: ProcessingMode
    edge_strategy: EdgeStrategy
    target_garments: tuple[str, ...]
    variants: tuple[str, ...]


def build_render_plan(policy: ProcessingPolicy, variants: tuple[str, ...]) -> RenderPlan:
    return RenderPlan(policy.mode, policy.edge_strategy, policy.target_garments, variants)


def apply_variant(rgba: np.ndarray, name: str, policy: ProcessingPolicy, plan: RenderPlan | None = None) -> np.ndarray:
    source = np.asarray(rgba, dtype=np.uint8)
    alpha = source[..., 3]
    selected_plan = plan or build_render_plan(policy, (name,))
    if name == VariantName.CONSERVATIVE.value:
        rendered_alpha = alpha
    elif name in {VariantName.ARTISTIC.value, VariantName.BINARY_ALPHA.value}:
        rendered_alpha = binary_alpha(alpha, 32 if name == VariantName.ARTISTIC.value else 128)
    elif name == VariantName.HALFTONE.value or selected_plan.edge_strategy is EdgeStrategy.HALFTONE or selected_plan.mode is ProcessingMode.HALFTONE_DARK_GARMENT:
        rendered_alpha = halftone_alpha(alpha, policy.halftone_cell)
    elif name == VariantName.CONTROLLED_SOFT_ALPHA.value or selected_plan.edge_strategy is EdgeStrategy.CONTROLLED_SOFT_ALPHA:
        rendered_alpha = np.clip(alpha.astype(np.int16) * 5 // 4, 0, 255).astype(np.uint8)
    elif selected_plan.edge_strategy is EdgeStrategy.BINARY_ALPHA:
        rendered_alpha = binary_alpha(alpha)
    else:
        rendered_alpha = alpha
    return canonicalize_hidden_rgb(np.dstack((source[..., :3], rendered_alpha)).astype(np.uint8))


def composite(rgba: np.ndarray, background: tuple[int, int, int], max_long_edge: int = 1024) -> np.ndarray:
    source = np.asarray(rgba, dtype=np.uint8)
    if max(source.shape[:2]) > max_long_edge:
        scale = max_long_edge / max(source.shape[:2])
        source = resize_rgba_premultiplied(source, (max(1, round(source.shape[1] * scale)), max(1, round(source.shape[0] * scale))))
    fg = source[..., :3].astype(np.float32)
    alpha = source[..., 3:4].astype(np.float32) / 255
    bg = np.full_like(fg, background, dtype=np.float32)
    return np.clip(fg * alpha + bg * (1 - alpha), 0, 255).astype(np.uint8)


def checkerboard(rgba: np.ndarray, cell: int = 32, max_long_edge: int = 1024) -> np.ndarray:
    source = np.asarray(rgba, dtype=np.uint8)
    if max(source.shape[:2]) > max_long_edge:
        scale = max_long_edge / max(source.shape[:2])
        source = resize_rgba_premultiplied(source, (max(1, round(source.shape[1] * scale)), max(1, round(source.shape[0] * scale))))
    yy, xx = np.indices(source.shape[:2])
    light = np.array([238, 238, 238], dtype=np.uint8)
    dark = np.array([180, 180, 180], dtype=np.uint8)
    bg = np.where(((xx // cell + yy // cell) % 2)[..., None] == 0, light, dark)
    return _composite_array(source, bg)


def dtg_underbase_preview(
    rgba: np.ndarray,
    garment: tuple[int, int, int],
    threshold: int = 24,
    spread: int = 1,
    max_long_edge: int = 1024,
) -> np.ndarray:
    """Approximate a white DTG underbase, explicitly not Printify's renderer."""
    source = np.asarray(rgba, dtype=np.uint8)
    if max(source.shape[:2]) > max_long_edge:
        scale = max_long_edge / max(source.shape[:2])
        source = resize_rgba_premultiplied(source, (max(1, round(source.shape[1] * scale)), max(1, round(source.shape[0] * scale))))
    alpha = source[..., 3].astype(np.int16)
    underbase = np.clip((alpha - threshold) * 255 // max(1, 255 - threshold), 0, 255).astype(np.uint8)
    if spread > 0:
        expanded = underbase.copy()
        for dy in range(-spread, spread + 1):
            for dx in range(-spread, spread + 1):
                expanded[max(0, dy):min(alpha.shape[0], alpha.shape[0] + dy), max(0, dx):min(alpha.shape[1], alpha.shape[1] + dx)] = np.maximum(
                    expanded[max(0, dy):min(alpha.shape[0], alpha.shape[0] + dy), max(0, dx):min(alpha.shape[1], alpha.shape[1] + dx)],
                    underbase[max(0, -dy):min(alpha.shape[0], alpha.shape[0] - dy), max(0, -dx):min(alpha.shape[1], alpha.shape[1] - dx)],
                )
        underbase = expanded
    canvas = np.full(source.shape[:2] + (3,), garment, dtype=np.uint8)
    white = np.full_like(canvas, 255)
    canvas = _composite_array(np.dstack((white, underbase)), canvas)
    return _composite_array(np.dstack((source[..., :3], source[..., 3])), canvas)


def _composite_array(rgba: np.ndarray, background: np.ndarray) -> np.ndarray:
    fg = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    return np.clip(fg * alpha + background.astype(np.float32) * (1 - alpha), 0, 255).astype(np.uint8)
