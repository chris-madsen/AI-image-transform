from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

import numpy as np

from .domain.models import MaskTuning, PhotopeaMaskPlan, ProcessingPolicy, ResolvedMaskBundle, VisualQualityAssessment


@dataclass(frozen=True, slots=True)
class PhotopeaCheckpoint:
    """Typed evidence returned by a Photopea mask session."""

    revision_id: str
    artifact_id: str
    source_hash: str


class PsdExporter(Protocol):
    def export(self, source: np.ndarray, artwork: np.ndarray, mask: np.ndarray) -> bytes: ...


class VisionProvider(Protocol):
    """External per-artwork vision decision boundary.

    Implementations belong to the Skill/agent adapter. The processing service
    never calls an LLM implicitly and never invents these values.
    """

    def resolve_masks(self, source: np.ndarray, policy: ProcessingPolicy) -> ResolvedMaskBundle: ...

    def choose_mask_tuning(self, source: np.ndarray, candidates: Mapping[str, np.ndarray]) -> MaskTuning: ...

    def assess_candidates(self, candidates: Mapping[str, np.ndarray]) -> VisualQualityAssessment: ...

    def review_photopea_checkpoint(self, checkpoint: PhotopeaCheckpoint) -> PhotopeaMaskPlan | None: ...


class ArtifactStore(Protocol):
    def job_dir(self, job_id: str) -> Path: ...
