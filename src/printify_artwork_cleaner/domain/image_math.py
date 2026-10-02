from __future__ import annotations

from collections import deque
from hashlib import sha256

import numpy as np

from .models import (
    AlphaProfile,
    ArtworkInspection,
    ImageGeometry,
    ProcessingPolicy,
)


def image_sha256(rgba: np.ndarray) -> str:
    return sha256(np.ascontiguousarray(rgba).tobytes()).hexdigest()


def alpha_profile(rgba: np.ndarray) -> AlphaProfile:
    alpha = np.asarray(rgba[..., 3], dtype=np.uint8)
    histogram = np.bincount(alpha.ravel(), minlength=256)
    hidden_rgb = int(np.count_nonzero(np.any(rgba[..., :3][alpha == 0] != 0, axis=-1)))
    total = int(alpha.size)
    return AlphaProfile(
        total=total,
        zero=int(histogram[0]),
        partial=int(total - histogram[0] - histogram[255]),
        full=int(histogram[255]),
        unique_levels=int(np.count_nonzero(histogram)),
        hidden_rgb_pixels=hidden_rgb,
    )


def _border_pixels(rgb: np.ndarray) -> np.ndarray:
    return np.concatenate((rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]), axis=0)


def edge_connected_background_mask(rgba: np.ndarray, tolerance: int) -> np.ndarray:
    """Return only pixels connected to the canvas edge and close to border color."""
    rgb = np.asarray(rgba[..., :3], dtype=np.int16)
    alpha = np.asarray(rgba[..., 3], dtype=np.uint8)
    height, width = alpha.shape
    border = _border_pixels(rgb)
    reference = np.median(border, axis=0).astype(np.int16)
    distance = np.max(np.abs(rgb - reference), axis=-1)
    eligible = distance <= int(tolerance)
    eligible |= alpha == 0
    mask = np.zeros((height, width), dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def seed(y: int, x: int) -> None:
        if eligible[y, x] and not mask[y, x]:
            mask[y, x] = True
            queue.append((y, x))

    for x in range(width):
        seed(0, x)
        seed(height - 1, x)
    for y in range(1, height - 1):
        seed(y, 0)
        seed(y, width - 1)

    while queue:
        y, x = queue.popleft()
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= next_y < height and 0 <= next_x < width and eligible[next_y, next_x] and not mask[next_y, next_x]:
                mask[next_y, next_x] = True
                queue.append((next_y, next_x))
    return mask


def protected_mask(policy: ProcessingPolicy, shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    result = np.zeros(shape, dtype=bool)
    for region in policy.protected_regions:
        left, top, right, bottom = region.pixels(width, height)
        result[top:bottom, left:right] = True
    return result


def inspect_rgba(rgba: np.ndarray, policy: ProcessingPolicy, source_bytes_sha256: str | None = None) -> tuple[ArtworkInspection, np.ndarray]:
    source = np.asarray(rgba, dtype=np.uint8)
    profile = alpha_profile(source)
    connected = edge_connected_background_mask(source, policy.background_tolerance)
    edge_alpha = source[..., 3][np.logical_or.reduce((
        np.pad(np.ones((1, source.shape[1]), dtype=bool), ((0, source.shape[0] - 1), (0, 0))),
        np.pad(np.ones((1, source.shape[1]), dtype=bool), ((source.shape[0] - 1, 0), (0, 0))),
        np.pad(np.ones((source.shape[0], 1), dtype=bool), ((0, 0), (0, source.shape[1] - 1))),
        np.pad(np.ones((source.shape[0], 1), dtype=bool), ((0, 0), (source.shape[1] - 1, 0))),
    ))]
    opaque_edge = bool(np.any(edge_alpha >= 250))
    connected_pixels = int(np.count_nonzero(connected))
    total = source.shape[0] * source.shape[1]
    crop_risk = opaque_edge and (connected_pixels < total * 0.02 or connected_pixels > total * 0.98)
    if profile.zero > 0 and profile.partial > 0:
        classification = "defective_transparent_edge"
    elif crop_risk:
        classification = "ambiguous_boundary_contact"
    elif connected_pixels >= total * 0.02:
        classification = "baked_external_background"
    else:
        classification = "intentional_or_ambiguous"
    warnings = ("artwork touches canvas boundary",) if crop_risk else ()
    inspection = ArtworkInspection(
        geometry=ImageGeometry(source.shape[1], source.shape[0], "RGBA", bool(profile.zero or profile.partial)),
        alpha=profile,
        classification=classification,
        border_connected_pixels=connected_pixels,
        crop_risk=crop_risk,
        source_sha256=source_bytes_sha256 or image_sha256(source),
        canonical_pixels_sha256=image_sha256(source),
        warnings=warnings,
    )
    return inspection, connected


def compose_alpha(source_alpha: np.ndarray, background: np.ndarray, protected: np.ndarray) -> np.ndarray:
    alpha = np.asarray(source_alpha, dtype=np.uint8).copy()
    alpha[np.asarray(background, dtype=bool) & ~np.asarray(protected, dtype=bool)] = 0
    return alpha


def canonicalize_hidden_rgb(rgba: np.ndarray) -> np.ndarray:
    result = np.asarray(rgba, dtype=np.uint8).copy()
    result[result[..., 3] == 0, :3] = 0
    return result


def resize_rgba_premultiplied(rgba: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    from PIL import Image

    source = np.asarray(rgba, dtype=np.float32) / 255.0
    alpha = source[..., 3:4]
    premultiplied = source[..., :3] * alpha
    channels = [
        np.asarray(Image.fromarray(np.clip(channel * 255, 0, 255).astype(np.uint8), mode="L").resize(size, Image.Resampling.LANCZOS), dtype=np.float32) / 255
        for channel in (*np.moveaxis(premultiplied, -1, 0), alpha[..., 0])
    ]
    resized_rgb = np.stack(channels[:3], axis=-1)
    resized_alpha = channels[3][..., None]
    rgb = np.divide(resized_rgb, np.maximum(resized_alpha, 1 / 255), out=np.zeros_like(resized_rgb), where=resized_alpha > 0)
    return np.dstack((np.clip(rgb * 255, 0, 255), np.clip(resized_alpha[..., 0] * 255, 0, 255))).astype(np.uint8)


def binary_alpha(alpha: np.ndarray, threshold: int = 128) -> np.ndarray:
    return np.where(np.asarray(alpha, dtype=np.uint8) >= threshold, 255, 0).astype(np.uint8)


def halftone_alpha(alpha: np.ndarray, cell: int = 8) -> np.ndarray:
    if cell < 2:
        raise ValueError("halftone cell must be >= 2")
    matrix = np.array(
        [[0, 48, 12, 60, 3, 51, 15, 63], [32, 16, 44, 28, 35, 19, 47, 31],
         [8, 56, 4, 52, 11, 59, 7, 55], [40, 24, 36, 20, 43, 27, 39, 23],
         [2, 50, 14, 62, 1, 49, 13, 61], [34, 18, 46, 30, 33, 17, 45, 29],
         [10, 58, 6, 54, 9, 57, 5, 53], [42, 26, 38, 22, 41, 25, 37, 23]], dtype=np.float32
    )
    # Scale the Bayer screen by the requested cell size. Different cells must
    # produce different dot frequencies; the old implementation ignored cell.
    screen = np.repeat(np.repeat((matrix + 0.5) / 64, cell, axis=0), cell, axis=1)
    screen = np.tile(screen, (1 + alpha.shape[0] // screen.shape[0], 1 + alpha.shape[1] // screen.shape[1]))
    screen = screen[: alpha.shape[0], : alpha.shape[1]]
    return np.where(np.asarray(alpha, dtype=np.float32) / 255 >= screen, 255, 0).astype(np.uint8)
