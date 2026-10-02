from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np


class PsdExporter(Protocol):
    def export(self, source: np.ndarray, artwork: np.ndarray, mask: np.ndarray) -> bytes: ...


class ArtifactStore(Protocol):
    def job_dir(self, job_id: str) -> Path: ...
