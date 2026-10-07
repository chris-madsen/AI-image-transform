from __future__ import annotations

import io
from hashlib import sha256

import numpy as np
from PIL import Image

from .models import (
    AlphaProfile,
    ArtworkInspection,
    ImageGeometry,
    ProcessingPolicy,
)


def image_sha256(rgba: np.ndarray) -> str:
    return sha256(np.ascontiguousarray(rgba).tobytes()).hexdigest()


def canonical_rgba_png_bytes(rgba: np.ndarray) -> bytes:
    """Serialize the normalized RGBA source exactly as external adapters do."""
    stream = io.BytesIO()
    Image.fromarray(np.asarray(rgba, dtype=np.uint8), mode="RGBA").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def canonical_png_sha256(rgba: np.ndarray) -> str:
    return sha256(canonical_rgba_png_bytes(rgba)).hexdigest()


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
    """Return the 4-connected edge selection used by Photopea's Magic Wand.

    The previous pixel-at-a-time queue had the right semantics but was not
    viable for 4500x5400 artwork.  Run-length connected-component labeling is
    equivalent for a binary eligible image, avoids a dependency on OpenCV or
    SciPy, and keeps the full-resolution selection inside the five-minute job
    budget.
    """
    rgb = np.asarray(rgba[..., :3], dtype=np.int16)
    alpha = np.asarray(rgba[..., 3], dtype=np.uint8)
    height, width = alpha.shape
    border = _border_pixels(rgb)
    reference = np.median(border, axis=0).astype(np.int16)
    distance = np.max(np.abs(rgb - reference), axis=-1)
    eligible = distance <= int(tolerance)
    eligible |= alpha == 0
    rows: list[list[tuple[int, int, int]]] = []
    parent: list[int] = []

    def new_label() -> int:
        label = len(parent)
        parent.append(label)
        return label

    def find(label: int) -> int:
        root = label
        while parent[root] != root:
            root = parent[root]
        while parent[label] != label:
            next_label = parent[label]
            parent[label] = root
            label = next_label
        return root

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    previous: list[tuple[int, int, int]] = []
    for y in range(height):
        row = eligible[y]
        starts = np.flatnonzero(row & ~np.r_[False, row[:-1]])
        ends = np.flatnonzero(row & ~np.r_[row[1:], False])
        current: list[tuple[int, int, int]] = []
        previous_index = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            while previous_index < len(previous) and previous[previous_index][1] < start:
                previous_index += 1
            overlaps: list[int] = []
            scan_index = previous_index
            while scan_index < len(previous) and previous[scan_index][0] <= end:
                overlaps.append(previous[scan_index][2])
                scan_index += 1
            label = overlaps[0] if overlaps else new_label()
            for other in overlaps[1:]:
                union(label, other)
            current.append((start, end, label))
        rows.append(current)
        previous = current

    border_roots: set[int] = set()
    for row_index in (0, height - 1):
        border_roots.update(find(label) for _, _, label in rows[row_index])
    border_roots.update(find(label) for row in rows for start, end, label in row if start == 0 or end == width - 1)

    mask = np.zeros((height, width), dtype=bool)
    for y, row in enumerate(rows):
        for start, end, label in row:
            if find(label) in border_roots:
                mask[y, start:end + 1] = True
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
    connected = edge_connected_background_mask(source, policy.effective_background_tolerance)
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


def compose_artistic_perimeter_alpha(
    rgba: np.ndarray,
    source_alpha: np.ndarray,
    removable_background: np.ndarray,
    protected: np.ndarray,
    low_distance: int = 4,
    full_distance: int = 64,
    band_radius: int = 4,
) -> np.ndarray:
    """Preserve an intentional external fade without retaining flat background.

    This is deliberately limited to the approved edge-connected removal mask.
    Interior pixels and protected details remain untouched. The ramp converts
    artwork pixels near the known flat background colour into controlled alpha,
    avoiding both a rectangular cut and a broad uniform glow.
    """
    source = np.asarray(rgba, dtype=np.uint8)
    alpha = np.asarray(source_alpha, dtype=np.uint8).copy()
    removable = np.asarray(removable_background, dtype=bool) & ~np.asarray(protected, dtype=bool)
    if not np.any(removable):
        return alpha
    # Only soften the perimeter of the approved removal. Applying the colour
    # ramp to every edge-connected background pixel creates a large translucent
    # veil when the source contains a broad, slightly tinted backdrop.
    retained = ~removable
    near_retained = retained.copy()
    for _ in range(max(0, int(band_radius))):
        expanded = near_retained.copy()
        expanded[1:] |= near_retained[:-1]
        expanded[:-1] |= near_retained[1:]
        expanded[:, 1:] |= near_retained[:, :-1]
        expanded[:, :-1] |= near_retained[:, 1:]
        near_retained = expanded
    perimeter = removable & near_retained
    border = _border_pixels(source[..., :3].astype(np.int16))
    background_colour = np.median(border, axis=0).astype(np.int16)
    distance = np.max(np.abs(source[..., :3].astype(np.int16) - background_colour), axis=-1)
    ramp = np.clip(
        (distance - int(low_distance)) * 255 // max(1, int(full_distance - low_distance)),
        0,
        255,
    ).astype(np.uint8)
    alpha[perimeter] = np.minimum(alpha[perimeter], ramp[perimeter])
    alpha[removable & ~perimeter] = 0
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
