# Requirement Evidence Matrix

This matrix records implementation evidence without treating a valid PSD
signature or a deterministic fixture as proof of production visual quality.

| Requirement area | Evidence | Status |
|---|---|---|
| Frozen policy and semantic-mask boundary | `domain/models.py`, `test_validation_and_psd.py::test_semantic_text_without_pixel_mask_is_not_passed` | Verified |
| Edge-connected external-perimeter cleanup | `domain/image_math.py`, `test_cleaner_domain.py::test_edge_connected_background_does_not_remove_internal_same_color` | Verified |
| Intact-reference precedence and protected RGB/alpha diffs | `ResolvedMaskBundle.protected_reference`, `ValidationResult` protected diff fields, validation regression tests | Verified |
| Unauthorized alpha-removal detection | `ValidationResult.unauthorized_alpha_removal_pixels`, validation regression test | Verified |
| Approved manual-perimeter fixture | `tests/fixtures/manual_perimeter/`, `test_golden_cleaner.py` | Verified |
| Owner-approved Panther golden comparator | `domain/golden_acceptance.py`, `tests/test_panther_golden_acceptance.py`, `scripts/validate_panther_golden.py` | Verified as a gate; the current deterministic proposal candidate fails it and remains unpromoted |
| Beauty-aware visual-quality gate | `VisualQualityAssessment`, protected-region checks, deterministic fragmentation/edge metrics, missing-evidence tests | Partial: external reviewer pixels are wired, but automatic model acceptance still requires deployment |
| Edge/fringe safety metrics | `domain/visual_quality.py`, `domain/validation.py`, report fields for chroma contamination, contour distance and dark-garment halo | Verified as deterministic safety signals; not a semantic substitute for the golden/reviewer gate |
| Real specialized model adapters | `adapters/model_proposals.py`, `scripts/serve_model_proposals.py`, `scripts/serve_sam2_protection.py`, model-stack tests | Partial: pinned BiRefNet/BEN2/SAM2 adapters are implemented, but deployment weights and Panther promotion remain external gates |
| Windows Vega 56 DirectML adapter | `scripts/serve_onnx_proposals.py`, `deployment/windows/`, `tests/test_onnx_windows_adapter.py` | Implemented: pinned ONNX file, DirectML-first/CPU-second provider selection, sequential single-request session, LAN deployment scripts and 1024/2048 benchmark; physical Windows GPU run remains deployment evidence |
| Public mask ownership boundary | `service.py`, Skill helper, `test_service_contract.py::test_public_job_rejects_authoritative_photopea_mask` | Verified: caller-supplied final Photopea masks and runtime quality claims are rejected |
| Missing specialized proposal is fail-closed | `service.py`, async contract test | Verified: unconfigured proposal provider cannot produce a passed job |
| Retrievable Photopea checkpoint pixels | `bridge/server.mjs`, `adapters/photopea.py`, `adapters/vision_review.py` | Verified in the current real smoke: authenticated source/artwork/mask/overlay and garment previews were downloaded; PSD binaries remain outside Git |
| Production checkpoint review loop | `service.py::_review_photopea_session`, typed HTTP reviewer, bridge session API | Partial: real session/review/finalize wiring passed with a deterministic acceptance fixture; deployed reviewer credentials and model remain required |
| HMAC-bound finalization | `review_acceptance_token`, bridge `validAcceptanceToken`, bridge contract tests | Verified: missing, stale or mismatched acceptance cannot finalize a checkpoint |
| One-document Photopea authoring | `bridge/server.mjs`, `test_bridge_contract.py` | Verified: one source document remains alive; initial transfer uses accepted and gaps carriers, revision transfer uses one correction carrier and no polygon/script input |
| Linked Photopea raster masks and editable fills | Photopea Action Manager scripts, reopened evidence layer list | Verified in current 4500×5400 smoke |
| PSD reopen/pixel validation | `decodePng`, exact checkpoint↔reopen pixel comparison, current smoke evidence | Verified: reopened artwork/mask/garment pixels and required layers were checked |
| Final PNG/PSD provenance | `service.py::_run_deferred_psd`, authoritative `artifact_set`, report contract tests | Verified: final PNGs, masks, previews and PSD are published from one accepted Photopea revision; core outputs remain proposals |
| Source hash at bridge boundary | `PhotopeaLiveSession.open`, `test_bridge_contract.py` and current session smoke | Verified: raw source bytes are hashed before Photopea launch and compared with the revision source hash |
| Full-resolution Photopea contract smoke | Fresh 2026-10-07 run with `PHOTOPEA_REVIEW_SECRET`: 4500×5400, 290.60 s, `passed`, verified PSD, reopened pixels and required layers | Verified for technical contract only; the deterministic proposal failed the owner Panther golden and is not production-approved |
| Five-minute budget | `PHOTOPEA_REVIEW_BUDGET_SECONDS`, bounded session/client timeouts, current smoke | Partial: current run completed within 300 s, but deployment model/reviewer latency must be benchmarked before SLA promotion |
| Async job/auth/idempotency/path safety | `tests/test_service_contract.py` and full suite | Verified |

The current full-resolution smoke command is intentionally recorded as an
external run rather than committed binary output:

```bash
PHOTOPEA_REVIEW_SECRET='injected-at-runtime' \
  .venv/bin/python /tmp/service_photopea_full_smoke_persistent.py
```

The PSD and generated PNGs must stay outside Git. The owner-approved Panther
golden gate remains unchecked for the current model fixture until a real local
specialized model and a real visual reviewer produce a passing candidate.
