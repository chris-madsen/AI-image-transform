#!/usr/bin/env python3
"""Validate a candidate RGBA render against the owner-approved Panther fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from printify_artwork_cleaner.domain.golden_acceptance import GoldenRegion, evaluate_golden_render


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/panther_golden"))
    args = parser.parse_args()
    manifest = json.loads((args.fixture / "manifest.json").read_text())
    approved = np.asarray(Image.open(args.fixture / str(manifest["approved_render_file"])).convert("RGBA"))
    candidate = np.asarray(Image.open(args.candidate).convert("RGBA"))
    tolerances = manifest["tolerances"]
    regions = tuple(GoldenRegion(name, *map(int, bounds)) for name, bounds in manifest["regions"].items())
    result = evaluate_golden_render(
        candidate,
        approved,
        regions,
        protected_rgb_max_delta=int(tolerances["protected_region_rgb_max_delta"]),
        protected_alpha_loss_pixels=int(tolerances["protected_region_alpha_loss_pixels"]),
        lower_fade_alpha_mae=float(tolerances["lower_fade_alpha_mae"]),
        external_edge_alpha_loss_pixels=int(tolerances["external_edge_alpha_loss_pixels"]),
    )
    print(json.dumps({"passed": result.passed, "errors": result.errors, "metrics": result.metrics}, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
