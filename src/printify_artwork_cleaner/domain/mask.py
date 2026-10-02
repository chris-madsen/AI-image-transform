from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

import numpy as np

from .models import MaskRevision


def create_mask_revision(
    alpha: np.ndarray,
    *,
    parent: MaskRevision | None = None,
    operations: tuple[str, ...] = (),
    confidence: float = 1.0,
) -> MaskRevision:
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be in [0, 1]")
    digest = sha256(np.ascontiguousarray(np.asarray(alpha, dtype=np.uint8)).tobytes()).hexdigest()
    return MaskRevision(
        revision_id=uuid4().hex,
        parent_id=parent.revision_id if parent else None,
        mask_sha256=digest,
        operations=tuple(operations),
        confidence=confidence,
    )
