from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from printify_artwork_cleaner.application import process_image_bytes
from printify_artwork_cleaner.domain.models import JobStatus, ProcessingPolicy


def _png(rgba: np.ndarray) -> bytes:
    stream = BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(stream, format="PNG")
    return stream.getvalue()


def _base() -> np.ndarray:
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[..., :3] = [110, 135, 165]
    rgba[..., 3] = 255
    return rgba


@pytest.fixture
def cases() -> list[tuple[str, np.ndarray, ProcessingPolicy, set[JobStatus]]]:
    cases: list[tuple[str, np.ndarray, ProcessingPolicy, set[JobStatus]]] = []

    animal = _base(); animal[18:48, 18:48, :3] = [35, 35, 35]
    animal[25:29, 25:29, :3] = [240, 240, 240]
    cases.append(("animal-text-splashes", animal, ProcessingPolicy(must_keep=("eyes", "text", "splashes")), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED}))

    vegetation = _base(); vegetation[20:46, 22:42, :3] = [45, 45, 45]; vegetation[12:25, 42:55, :3] = [20, 150, 60]
    cases.append(("vegetation", vegetation, ProcessingPolicy(keep_if_intentional=("leaves",)), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED}))

    light_detail = _base(); light_detail[18:48, 18:48, :3] = [20, 20, 20]; light_detail[28:36, 28:36, :3] = [235, 235, 235]
    cases.append(("light-internal-detail", light_detail, ProcessingPolicy(must_keep=("light detail",)), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED}))

    typography = _base(); typography_image = Image.fromarray(typography, mode="RGBA"); ImageDraw.Draw(typography_image).text((20, 25), "A", fill=(255, 255, 255, 255)); typography = np.asarray(typography_image).copy()
    cases.append(("typography", typography, ProcessingPolicy(must_keep=("all text",)), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}))

    smoke = _base(); smoke[20:44, 20:44, :3] = [150, 150, 150]; smoke[20:44, 20:44, 3] = 80
    cases.append(("smoke", smoke, ProcessingPolicy(keep_if_intentional=("smoke",)), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED}))

    checker = _base(); checker[::4, ::4, :3] = [238, 238, 238]; checker[1::4, 1::4, :3] = [180, 180, 180]
    cases.append(("baked-checkerboard", checker, ProcessingPolicy(), {JobStatus.PASSED, JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}))

    boundary = _base(); boundary[:, 0:6, :3] = [20, 20, 20]
    cases.append(("boundary-touching", boundary, ProcessingPolicy(), {JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}))

    ambiguous = np.full((64, 64, 4), [30, 30, 30, 255], dtype=np.uint8)
    cases.append(("ambiguous", ambiguous, ProcessingPolicy(), {JobStatus.REFUSED, JobStatus.REVIEW_REQUIRED}))
    return cases


@pytest.mark.parametrize("index", range(8))
def test_golden_classes_produce_explicit_safe_decisions(cases, index: int, tmp_path: Path) -> None:
    name, source, policy, allowed = cases[index]
    report = process_image_bytes(_png(source), policy, tmp_path / name)
    # No fixture may claim success while the mandatory Photopea/PSD stage is
    # unavailable. Ambiguous cases are therefore explicit review decisions.
    assert report.status is JobStatus.REVIEW_REQUIRED
    if policy.must_keep or policy.keep_if_intentional or policy.remove_only:
        assert "semantic_masks" in report.validation.review_regions
    assert report.artifacts
    assert report.inspection.source_sha256
