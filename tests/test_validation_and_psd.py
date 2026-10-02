from __future__ import annotations

import numpy as np
from PIL import Image
from io import BytesIO

from printify_artwork_cleaner.domain.image_math import inspect_rgba, protected_mask
from printify_artwork_cleaner.domain.models import ProcessingPolicy, JobStatus
from printify_artwork_cleaner.domain.validation import validate_candidate
from printify_artwork_cleaner.application import process_image_bytes


def test_partial_alpha_halo_is_not_passed() -> None:
    source = np.zeros((16, 16, 4), dtype=np.uint8)
    source[..., :3] = [200, 20, 20]
    source[..., 3] = 255
    candidate = source.copy()
    candidate[..., 3] = 32
    policy = ProcessingPolicy()
    inspection, _ = inspect_rgba(source, policy)
    result = validate_candidate(candidate, source, inspection, policy, protected_mask(policy, source.shape[:2]))
    assert result.status in {JobStatus.REVIEW_REQUIRED, JobStatus.REFUSED}
    assert "halo" in result.review_regions


def test_photopea_exporter_contract_is_binary_psd() -> None:
    source = np.zeros((8, 10, 4), dtype=np.uint8)
    source[..., :3] = [20, 40, 60]
    source[..., 3] = 255
    mask = np.full((8, 10), 255, dtype=np.uint8)
    class FakePhotopeaExporter:
        def export(self, received_source, artwork, received_mask) -> bytes:
            assert received_source.shape == source.shape
            assert artwork.shape == source.shape
            assert received_mask.shape == mask.shape
            return b"8BPS" + b"photopea-live-result"

    result = FakePhotopeaExporter().export(source, source, mask)
    assert result.startswith(b"8BPS")


def test_missing_photopea_live_api_is_review_required(tmp_path) -> None:
    stream = BytesIO()
    Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA").save(stream, format="PNG")
    report = process_image_bytes(stream.getvalue(), ProcessingPolicy(), tmp_path)
    assert report.status is JobStatus.REVIEW_REQUIRED
    assert "photopea_live_api" in report.validation.review_regions
    assert not any(artifact.name.endswith(".psd") for artifact in report.artifacts)
