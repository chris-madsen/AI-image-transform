# Requirement Evidence Matrix

This matrix records implementation evidence without treating a valid PSD signature
as proof of editable structure.

| Requirement area | Evidence | Status |
|---|---|---|
| Frozen policy and explicit semantic-mask boundary | `src/printify_artwork_cleaner/domain/models.py`, `tests/test_validation_and_psd.py::test_semantic_text_without_pixel_mask_is_not_passed` | Verified |
| Edge-connected external-perimeter cleanup | `src/printify_artwork_cleaner/domain/image_math.py`, `tests/test_cleaner_domain.py::test_edge_connected_background_does_not_remove_internal_same_color` | Verified |
| Intact-reference precedence | `ResolvedMaskBundle.protected_reference`, `tests/test_validation_and_psd.py::test_intact_reference_wins_and_reports_zero_protected_diffs` | Verified |
| Protected alpha/RGB diff evidence | `ValidationResult.protected_alpha_loss_pixels`, `protected_rgb_diff_pixels` | Verified |
| Unauthorized alpha-removal detection | `ValidationResult.unauthorized_alpha_removal_pixels`, corresponding validation regression test | Verified |
| Approved manual-perimeter golden fixture | `tests/fixtures/manual_perimeter/`, `tests/test_golden_cleaner.py::test_manual_perimeter_fixture_matches_approved_alpha_and_preserves_details` | Verified |
| Beauty-aware visual quality gate | `VisualQualityAssessment`, deterministic fragmentation guard, `test_missing_visual_quality_assessment_is_review_required`, low-score override test | Verified |
| Real specialized model smoke | Deployment-only BiRefNet/BEN2 HTTP adapters with independent model metadata and weights hashes; the consensus candidate was visually inspected and rejected by the Panther golden validator because of halo, missing perimeter detail, and lower-fade mismatch | Partial: evidence is real, but production promotion remains blocked |
| Protected eyes/text/vegetation/internal hole | Manual-perimeter fixture and golden test | Verified |
| Dark-garment preview distinction | `test_manual_perimeter_fixture_has_distinct_dark_garment_preview`, DTG tests | Verified |
| Public mask ownership boundary | `service.py`, `submit_artwork_job.py`, `tests/test_service_contract.py::test_public_job_rejects_authoritative_photopea_mask`, public `freeze_policy` rejection | Verified: caller-supplied final Photopea masks are rejected |
| Specialized proposal adapter boundary | `adapters/model_proposals.py`, `tests/test_model_proposals.py` | Partial: pinned BiRefNet/BEN2 HTTP adapters, per-artwork tuning/quality evidence and consensus are implemented; deployment endpoints and real weights still must be configured |
| Missing specialized proposal is fail-closed | `service.py`, `tests/test_service_contract.py::test_async_job_contract_and_artifacts` | Verified: an unconfigured provider adds `model_proposal` review evidence and cannot produce a passed job |
| Full-resolution Panther golden acceptance | `tests/fixtures/panther_golden/`, `domain/golden_acceptance.py`, `tests/test_panther_golden_acceptance.py`, `scripts/validate_panther_golden.py` | Verified: approved RESTORED render extracted from the owner PSD; ears, eyes, whiskers, head foliage, lower fade and external-edge mutations are rejected |
| Independent model pins | `docs/deployment/model-stack.md`, `adapters/model_proposals.py`, `tests/test_model_proposals.py` | Partial: independent BiRefNet/BEN2 metadata pins are enforced; actual model endpoints, SAM 2.1/ViTMatte adapters and weights remain deployment work |
| Retrievable Photopea checkpoint artifacts | `bridge/server.mjs`, `adapters/photopea.py`, `artifacts/photopea-full-smoke-current-20261006/job-evidence.json` | Verified: authenticated checkpoint URLs were returned and downloaded in the full job-level smoke |
| Production checkpoint review loop | `service.py::_review_photopea_session`, `adapters/vision_review.py`, `tests/test_vision_review.py`, `artifacts/photopea-full-smoke-current-20261006/correction-job-evidence.json` | Partial: typed HTTP reviewer adapter, live acceptance/correction path and hash-bound revision are verified; a deployed external reviewer endpoint remains deployment work |
| Async job, authentication, idempotency and path safety | `tests/test_service_contract.py` and full suite | Verified |
| Real Photopea source + raster-carrier transfer | `bridge/server.mjs`, one source + one correction-mask carrier per revision, tokenized ArrayBuffer endpoints, no polygon or seven-PNG primary path; `artifacts/photopea-full-smoke-current-20261006/job-evidence.json` | Verified for 8×8 revision and full-resolution job-level smoke |
| Linked Photopea raster mask | Canonical charID transparency-selection sequence and linked mask creation in the bridge; revision mask SHA changes and full job evidence | Verified for 8×8 initial+revision and full-resolution initial job |
| Real editable garment-fill layers | Solid Color Fill content-layer Action Manager path for black/navy/blue-jean; revision previews are independently exported and reopened | Verified for 8×8 initial+revision and full-resolution initial job |
| PSD reopen/structure validation | `decodePng`, source+mask render comparison, exact checkpoint↔reopen pixel comparison and `artifacts/photopea-full-smoke-current-20261006/job-evidence.json` | Verified for 8×8 initial+revision and full-resolution job-level smoke |
| PSD visual/mask equivalence validation | `decodePng`, source+mask render comparison, exact checkpoint↔reopen pixel comparison and full-resolution evidence | Verified for 8×8 initial+revision and full-resolution job-level smoke |
| Full-resolution Photopea session/export proof | `artifacts/photopea-full-smoke-current-20261006/evidence.json`, `job-evidence.json` | Verified: 4500×5400 session, checkpoint in 75.4 s, final PSD in 194.57 s, full job in 265.81 s, reopened pixel evidence and 8BPS PSD |
| Full-resolution job-level Photopea proof | `artifacts/photopea-full-smoke-current-20261006/job-evidence.json`, command recorded in the artifact | Verified: async POST → poll completed with `passed` and `psd_export_status=verified` in 265.81 s |
