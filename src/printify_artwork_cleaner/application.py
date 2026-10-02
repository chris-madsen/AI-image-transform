from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .adapters.photopea import PhotopeaLiveApiUnavailable
from .domain.image_math import compose_alpha, inspect_rgba, protected_mask
from .domain.models import Artifact, JobStatus, ProcessingPolicy, ProcessingReport
from .domain.rendering import BACKGROUNDS, apply_variant, checkerboard, composite
from .domain.validation import validate_candidate

PIPELINE_VERSION = "2026.10.02.1"


def _save_rgba(rgba: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", dpi=(300, 300), optimize=False)


def _save_rgb(rgb: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG", optimize=False)


def _write_artifact(path: Path, name: str, media_type: str) -> Artifact:
    import hashlib

    return Artifact(name, name, media_type, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def process_image_bytes(source_bytes: bytes, policy: ProcessingPolicy, output_dir: Path, psd_exporter=None) -> ProcessingReport:
    with Image.open(__import__("io").BytesIO(source_bytes)) as image:
        source = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    inspection, background = inspect_rgba(source, policy)
    protected = protected_mask(policy, source.shape[:2])
    alpha = compose_alpha(source[..., 3], background, protected)
    base = np.dstack((source[..., :3], alpha)).astype(np.uint8)
    variants = tuple(dict.fromkeys(policy.requested_variants or ("conservative", "artistic")))
    outputs: dict[str, np.ndarray] = {name: apply_variant(base, name, policy) for name in variants}
    chosen = outputs.get("conservative", next(iter(outputs.values())))
    validation = validate_candidate(chosen, source, inspection, policy, protected)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Artifact] = []
    for name, rgba in outputs.items():
        path = output_dir / f"artwork_{name}.png"
        _save_rgba(rgba, path)
        artifacts.append(_write_artifact(path, path.name, "image/png"))
        for background_name, color in BACKGROUNDS.items():
            preview_path = output_dir / f"preview_{name}_{background_name}.png"
            _save_rgb(composite(rgba, color), preview_path)
            artifacts.append(_write_artifact(preview_path, preview_path.name, "image/png"))
        checker_path = output_dir / f"preview_{name}_checkerboard.png"
        _save_rgb(checkerboard(rgba), checker_path)
        artifacts.append(_write_artifact(checker_path, checker_path.name, "image/png"))
        mask_path = output_dir / f"mask_{name}.png"
        _save_rgb(np.repeat(rgba[..., 3, None], 3, axis=-1), mask_path)
        artifacts.append(_write_artifact(mask_path, mask_path.name, "image/png"))

    dtg_path = output_dir / "preview_dtg_underbase.png"
    _save_rgb(composite(chosen, (255, 255, 255)), dtg_path)
    artifacts.append(_write_artifact(dtg_path, dtg_path.name, "image/png"))
    alpha_path = output_dir / "alpha_mask.png"
    _save_rgb(np.repeat(chosen[..., 3, None], 3, axis=-1), alpha_path)
    artifacts.append(_write_artifact(alpha_path, alpha_path.name, "image/png"))
    bridge_warning: str | None = None
    if psd_exporter is not None:
        psd_path = output_dir / "artwork_editable.psd"
        try:
            psd_path.write_bytes(psd_exporter.export(source, chosen, chosen[..., 3]))
            artifacts.append(_write_artifact(psd_path, psd_path.name, "image/vnd.adobe.photoshop"))
        except PhotopeaLiveApiUnavailable as exc:
            bridge_warning = f"photopea_live_api_unavailable: {exc}"
    else:
        bridge_warning = "photopea_live_api_not_configured"

    if bridge_warning:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, bridge_warning), review_regions=(*validation.review_regions, "photopea_live_api"))
    report = ProcessingReport(
        status=validation.status,
        inspection=inspection,
        validation=validation,
        pipeline_version=PIPELINE_VERSION,
        edge_strategy=policy.edge_strategy.value,
        variants=variants,
        artifacts=tuple(artifacts),
        changed_rgb=validation.changed_pixels > 0,
    )
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps({"policy": asdict(policy), **report.as_dict()}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    artifacts.append(_write_artifact(report_path, report_path.name, "application/json"))
    return replace(report, artifacts=tuple(artifacts))
