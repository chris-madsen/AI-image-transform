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
| Real Photopea source/art/mask layer transfer | `bridge/server.mjs`, typed one-source session path; legacy 32x32 fixture has non-empty named layers and no `Layer 1` | Partial; current Photopea polygon action fails fast and no full-resolution PSD is claimed |
| Linked Photopea raster mask | Canonical Action Manager sequence in the bridge; session path requires a verified polygon selection before mask creation | Partial; current runtime rejects the polygon action |
| Real garment-fill layers in a passed PSD | Five filled raster layers are created below working art and found during PSD reopen | Verified on fixture |
| PSD reopen/structure validation | 32x32 fixture emitted `PHOTOPEA_STRUCTURE_BUILT`; new one-source session returns explicit `502` in 3 seconds on the current polygon runtime error | Partial; round-trip remains pending |
| PSD visual/mask equivalence validation | The full-resolution result contains black/navy/blue-jean previews, an alpha mask, and a Photopea-reopened linked raster mask; direct PSD-channel pixel extraction remains a follow-up fixture | Partial |
| Full-resolution job-level Photopea proof | Full-resolution Photopea attempts were bounded at 300 seconds and timed out; no new PSD is claimed as final | Partial; PNG core is available, PSD round-trip pending |
