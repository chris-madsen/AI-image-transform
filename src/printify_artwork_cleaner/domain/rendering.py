from __future__ import annotations

from typing import Mapping

import numpy as np

from .image_math import binary_alpha, canonicalize_hidden_rgb, halftone_alpha, resize_rgba_premultiplied
from .models import EdgeStrategy, ProcessingPolicy


BACKGROUNDS: Mapping[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (119, 119, 119),
    "navy": (54, 75, 99),
    "blue_jean": (110, 142, 174),
}


def apply_variant(rgba: np.ndarray, name: str, policy: ProcessingPolicy) -> np.ndarray:
    source = np.asarray(rgba, dtype=np.uint8)
    alpha = source[..., 3]
    if name == "conservative":
        rendered_alpha = alpha
    elif name == "artistic":
        rendered_alpha = binary_alpha(alpha, 32)
    elif policy.edge_strategy in {EdgeStrategy.BINARY_ALPHA, EdgeStrategy.HALFTONE} or name == "halftone":
        rendered_alpha = halftone_alpha(alpha, policy.halftone_cell)
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


def _composite_array(rgba: np.ndarray, background: np.ndarray) -> np.ndarray:
    fg = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    return np.clip(fg * alpha + background.astype(np.float32) * (1 - alpha), 0, 255).astype(np.uint8)
