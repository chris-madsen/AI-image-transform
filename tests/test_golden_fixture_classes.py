from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from printify_artwork_cleaner.domain.image_math import compose_alpha

ROOT = Path(__file__).parent / "fixtures" / "golden_classes"


def _load(name: str) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    directory = ROOT / name
    manifest = json.loads((directory / "manifest.json").read_text())
    arrays = []
    for key in ("source_file", "protection_file", "removal_file", "expected_file"):
        path = directory / manifest[key]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest[key.replace("_file", "_sha256")]
        mode = "RGBA" if key in {"source_file", "expected_file"} else "L"
        arrays.append(np.asarray(Image.open(path).convert(mode), dtype=np.uint8))
    return manifest, *arrays


def test_all_golden_classes_preserve_protected_pixels_and_expected_alpha() -> None:
    names = sorted(path.parent.name for path in ROOT.glob("*/manifest.json"))
    assert names == [
        "ambiguous",
        "animal_text_splashes",
        "baked_checkerboard",
        "boundary_touching",
        "light_internal_details",
        "smoke",
        "typography",
        "vegetation",
    ]
    for name in names:
        manifest, source, protection, removal, expected = _load(name)
        protected = protection > 0
        removable = removal > 0
        actual_alpha = compose_alpha(source[..., 3], removable, protected)
        assert np.array_equal(actual_alpha, expected[..., 3]), name
        assert np.array_equal(expected[protected, :3], source[protected, :3]), name
        assert np.count_nonzero(expected[protected, 3] == 0) == 0, name
        assert manifest["expected_status"] in {"passed", "review_required"}


def test_ambiguous_golden_classes_are_not_auto_accepted() -> None:
    for name in ("ambiguous", "baked_checkerboard", "boundary_touching"):
        manifest, *_ = _load(name)
        assert manifest["expected_status"] == "review_required"
