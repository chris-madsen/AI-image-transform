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
| Protected eyes/text/vegetation/internal hole | Manual-perimeter fixture and golden test | Verified |
| Dark-garment preview distinction | `test_manual_perimeter_fixture_has_distinct_dark_garment_preview`, DTG tests | Verified |
| Async job, authentication, idempotency and path safety | Existing service contract suite, 32 passing tests | Verified |
| Real Photopea source + raster-carrier transfer | `bridge/server.mjs`, one source + one mask carrier, tokenized ArrayBuffer endpoints, no polygon or seven-PNG primary path; live 8×8 smoke completed | Verified for live smoke fixture |
| Linked Photopea raster mask | Canonical charID transparency-selection sequence and linked mask creation in the bridge; reopened PSD mask pixels equal the accepted checkpoint | Verified for live smoke fixture |
| Real editable garment-fill layers | Solid Color Fill content-layer Action Manager path for black/navy/blue-jean; all three previews independently match expected renders after reopen | Verified for live smoke fixture |
| PSD reopen/structure validation | Live PSD begins with `8BPS`, contains the required layer set, and passes exact reopened-pixel comparison | Verified for live smoke fixture |
| PSD visual/mask equivalence validation | `decodePng`, source+mask render comparison, exact checkpoint↔reopen pixel comparison and hash-bound adapter evidence | Verified for 8×8, 1000×1200, and `4500×5400` live fixtures |
| Full-resolution Photopea session/export proof | `artifacts/photopea-full-smoke-20261006/`, `PhotopeaSessionClient`, returned `8BPS` PSD, exact reopened pixel evidence, 232.39 s total | Verified for direct Photopea session/export; external job-level POST → poll remains pending |
| Full-resolution job-level Photopea proof | Async service job publication and POST → poll integration evidence | Not verified; task 5.4 remains explicitly unchecked |
