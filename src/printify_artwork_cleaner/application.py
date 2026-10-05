from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .adapters.photopea import PhotopeaLiveApiUnavailable
from .domain.image_math import compose_alpha, compose_artistic_perimeter_alpha, inspect_rgba, protected_mask, resize_rgba_premultiplied
from .domain.models import Artifact, JobStatus, ProcessingMode, ProcessingPolicy, ProcessingReport, ResolvedMaskBundle, StageStatus
from .domain.rendering import BACKGROUNDS, apply_variant, build_render_plan, checkerboard, composite, dtg_underbase_preview
from .domain.validation import validate_candidate

PIPELINE_VERSION = "2026.10.03.1"


def _save_rgba(rgba: np.ndarray, path: Path, dpi: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", dpi=(dpi, dpi), optimize=False)


def _save_rgb(rgb: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG", optimize=False)


def _write_artifact(path: Path, name: str, media_type: str) -> Artifact:
    import hashlib

    return Artifact(name, name, media_type, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def _apply_canvas(rgba: np.ndarray, policy: ProcessingPolicy) -> np.ndarray:
    if policy.canvas_width is None or policy.canvas_height is None:
        return rgba
    target_w, target_h = policy.canvas_width, policy.canvas_height
    margin = min(policy.canvas_margin, target_w // 2, target_h // 2)
    available_w, available_h = target_w - 2 * margin, target_h - 2 * margin
    scale = min(available_w / rgba.shape[1], available_h / rgba.shape[0])
    resized = resize_rgba_premultiplied(rgba, (max(1, round(rgba.shape[1] * scale)), max(1, round(rgba.shape[0] * scale))))
    canvas = np.zeros((target_h, target_w, 4), dtype=np.uint8)
    left = (target_w - resized.shape[1]) // 2
    top = (target_h - resized.shape[0]) // 2
    canvas[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
    return canvas


def process_image_bytes(
    source_bytes: bytes,
    policy: ProcessingPolicy,
    output_dir: Path,
    psd_exporter=None,
    resolved_masks: ResolvedMaskBundle | None = None,
    authoritative_mask: np.ndarray | None = None,
) -> ProcessingReport:
    with Image.open(__import__("io").BytesIO(source_bytes)) as image:
        source = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    inspection, background = inspect_rgba(source, policy, hashlib.sha256(source_bytes).hexdigest())
    protected = protected_mask(policy, source.shape[:2])
    semantic_requested = bool(policy.must_keep or policy.keep_if_intentional or policy.remove_only)
    semantic_mask_missing = semantic_requested and resolved_masks is None
    removal = np.asarray(background, dtype=bool)
    if resolved_masks is not None and resolved_masks.removable_background is not None:
        removal |= np.asarray(resolved_masks.removable_background, dtype=bool)
    if resolved_masks is not None and resolved_masks.semantic_protection is not None:
        protected |= np.asarray(resolved_masks.semantic_protection, dtype=bool)
    reference = source.copy()
    if resolved_masks is not None and resolved_masks.protected_reference is not None:
        protected_reference = np.asarray(resolved_masks.protected_reference, dtype=np.uint8)
        if protected_reference.shape != source.shape:
            raise ValueError("protected reference must match source dimensions and RGBA channels")
        reference[protected, :] = protected_reference[protected, :]
    if authoritative_mask is not None:
        authoritative = np.asarray(authoritative_mask, dtype=np.uint8)
        if authoritative.shape != source.shape[:2]:
            raise ValueError("authoritative raster mask must match source dimensions")
        alpha = authoritative.copy()
    else:
        alpha = compose_alpha(reference[..., 3], removal, protected)
    base = np.dstack((reference[..., :3], alpha)).astype(np.uint8)
    base = _apply_canvas(base, policy)
    tuning = policy.mask_tuning
    artistic_alpha = authoritative.copy() if authoritative_mask is not None else compose_artistic_perimeter_alpha(
        reference, reference[..., 3], removal, protected,
        low_distance=tuning.fade_low_distance if tuning else 4,
        full_distance=tuning.fade_full_distance if tuning else 64,
        band_radius=tuning.fade_band_radius if tuning else 4,
    )
    artistic_base = _apply_canvas(np.dstack((reference[..., :3], artistic_alpha)).astype(np.uint8), policy)
    validation_source = _apply_canvas(reference, policy)
    variants = tuple(dict.fromkeys(policy.requested_variants or ("conservative", "artistic")))
    if policy.mode is ProcessingMode.INSPECT:
        variants = ("conservative",)
    render_plan = build_render_plan(policy, variants)
    outputs: dict[str, np.ndarray] = {
        name: apply_variant(artistic_base if name == "artistic" else base, name, policy, render_plan)
        for name in variants
    }
    validation_protected = _apply_canvas(np.dstack((protected.astype(np.uint8) * 255,) * 3 + (protected.astype(np.uint8) * 255,)), policy)[..., 3] > 0 if policy.canvas_width else protected
    allowed_removal = _apply_canvas(np.dstack((removal.astype(np.uint8) * 255,) * 4), policy)[..., 3] > 0 if policy.canvas_width else removal
    validations = {name: validate_candidate(output, validation_source, inspection, policy, validation_protected, allowed_removal) for name, output in outputs.items()}
    visual_quality = policy.visual_quality
    artistic_is_preferred = (
        "artistic" in outputs
        and visual_quality is not None
        and visual_quality.edge_naturalness >= 0.8
        and visual_quality.intentional_detail_score >= 0.8
    )
    chosen_name = "artistic" if artistic_is_preferred else ("conservative" if "conservative" in outputs else variants[0])
    chosen = outputs[chosen_name]
    validation = validations[chosen_name]
    if semantic_mask_missing:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "semantic_policy_has_no_pixel_masks"), review_regions=(*validation.review_regions, "semantic_masks"))
    if policy.mask_tuning is None:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "vision_mask_tuning_missing"), review_regions=(*validation.review_regions, "vision_mask_tuning"))
    elif policy.mask_tuning.confidence < 0.75:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "vision_mask_tuning_low_confidence"), review_regions=(*validation.review_regions, "vision_mask_tuning"))
    elif policy.mask_tuning.source_sha256 and policy.mask_tuning.source_sha256 != inspection.source_sha256:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "vision_mask_tuning_source_mismatch"), review_regions=(*validation.review_regions, "vision_mask_tuning"))
    if policy.visual_quality is not None and policy.visual_quality.source_sha256 and policy.visual_quality.source_sha256 != inspection.source_sha256:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "visual_quality_source_mismatch"), review_regions=(*validation.review_regions, "visual_quality"))
    if policy.mode is ProcessingMode.INSPECT:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "inspect_mode_does_not_process_artwork"), review_regions=(*validation.review_regions, "inspect_mode"))
    failing_variants = tuple(name for name, result in validations.items() if result.status is not JobStatus.PASSED)
    if failing_variants:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, f"variant_validation_failed:{','.join(failing_variants)}"), review_regions=(*validation.review_regions, "variant_validation"))
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Artifact] = []
    for name, rgba in outputs.items():
        path = output_dir / f"artwork_{name}.png"
        _save_rgba(rgba, path, policy.canvas_dpi)
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
    garment_name = next((name for name in policy.target_garments if name in BACKGROUNDS), "navy")
    _save_rgb(dtg_underbase_preview(chosen, BACKGROUNDS[garment_name]), dtg_path)
    artifacts.append(_write_artifact(dtg_path, dtg_path.name, "image/png"))
    alpha_path = output_dir / "alpha_mask.png"
    _save_rgb(np.repeat(chosen[..., 3, None], 3, axis=-1), alpha_path)
    artifacts.append(_write_artifact(alpha_path, alpha_path.name, "image/png"))
    bridge_warning: str | None = None
    photopea_status = "not_configured"
    psd_status = "not_checked"
    if psd_exporter is not None:
        psd_path = output_dir / "artwork_editable.psd"
        try:
            if getattr(psd_exporter, "supports_photopea_session", False):
                if policy.photopea_mask_revision is None:
                    raise PhotopeaLiveApiUnavailable("photopea_mask_revision is required for Photopea-authored masks")
                if policy.photopea_mask_revision.source_sha256 != inspection.source_sha256:
                    raise PhotopeaLiveApiUnavailable("raster revision source_sha256 does not match frozen source bytes")
                if hashlib.sha256(chosen[..., 3].tobytes()).hexdigest() != policy.photopea_mask_revision.result_mask_sha256:
                    raise PhotopeaLiveApiUnavailable("raster revision result_mask_sha256 does not match accepted candidate")
                export_kwargs = {"mask_revision": asdict(policy.photopea_mask_revision)}
            else:
                export_kwargs = {"variants": outputs} if getattr(psd_exporter, "supports_variants", False) else {}
            psd_path.write_bytes(psd_exporter.export(validation_source, chosen, chosen[..., 3], **export_kwargs))
            artifacts.append(_write_artifact(psd_path, psd_path.name, "image/vnd.adobe.photoshop"))
            photopea_status = "passed"
            has_pixel_evidence = getattr(psd_exporter, "round_trip_verified", False) and getattr(psd_exporter, "evidence", None) is not None
            psd_status = "passed" if has_pixel_evidence else "unverified_payload"
        except PhotopeaLiveApiUnavailable as exc:
            bridge_warning = f"photopea_live_api_unavailable: {exc}"
            photopea_status = "failed"
            psd_status = "failed"
    else:
        bridge_warning = "photopea_live_api_not_configured"

    if bridge_warning:
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, bridge_warning), review_regions=(*validation.review_regions, "photopea_live_api"))
    if psd_status != "passed":
        validation = replace(validation, status=JobStatus.REVIEW_REQUIRED, warnings=(*validation.warnings, "psd_structure_unverified"), review_regions=(*validation.review_regions, "psd_validation"))
    ai_mask_status = (
        "review_required"
        if semantic_mask_missing
        else ("provided" if resolved_masks else ("review_required" if policy.mask_tuning is None else "vision_decision_only"))
    )
    stage = StageStatus(
        ai_mask_status=ai_mask_status,
        photopea_processing_status=photopea_status,
        psd_validation_status=psd_status,
        png_validation_status="passed" if not failing_variants else "review_required",
        overall_status=validation.status,
    )
    report = ProcessingReport(
        status=validation.status,
        inspection=inspection,
        validation=validation,
        pipeline_version=PIPELINE_VERSION,
        edge_strategy=policy.edge_strategy.value,
        variants=variants,
        artifacts=tuple(artifacts),
        changed_rgb=validation.changed_pixels > 0,
        stage_status=stage,
        variant_validations=validations,
        photopea_revision=asdict(policy.photopea_mask_revision) if policy.photopea_mask_revision else None,
    )
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps({"policy": asdict(policy), **report.as_dict()}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    artifacts.append(_write_artifact(report_path, report_path.name, "application/json"))
    return replace(report, artifacts=tuple(artifacts))
