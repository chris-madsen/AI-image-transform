# AI Image Transform / Photopea Pipeline Review

**Date:** 2026-10-06
**Scope:** Follow-up audit after the Photopea raster-mask and production-runtime corrections.
**Decision:** Core correction work is verified; deployment-dependent model and reviewer stages remain explicitly incomplete.

## Verified corrections

- `photopea_mask` and `photopea_mask_revision` are not public job inputs.
- Photopea receives one source ArrayBuffer and one internal grayscale mask/correction carrier. The primary path no longer imports seven full-size PNG documents, polygon plans, or arbitrary scripts.
- The Photopea bridge authors the working mask, linked raster masks, source backup, restored/gap layers, and independently toggleable black/navy/blue-jean fills.
- The service keeps one outer Photopea browser session through the bounded review loop. The current runtime rebuilds the editable document from the frozen source plus the accepted correction carrier on each revision; this is documented honestly and is not claimed to be literal same-document mutation.
- Checkpoint artwork, mask, and dark-garment previews are returned as authenticated retrievable artifacts, not hashes alone.
- Reviewer decisions and corrections are typed and bound to source, checkpoint, parent revision, base-mask, and result-mask hashes. Stale revisions, wrong dimensions, arbitrary scripts, and polygon plans are rejected.
- Missing model proposals, missing visual-quality evidence, missing reviewer decisions, and missing Photopea conformance evidence fail closed to `review_required`.
- PSD acceptance requires reopen/pixel evidence and required editable layers. A valid `8BPS` signature alone cannot produce `passed`.
- PSD/PSB binaries are ignored by Git. The repository records reproducible evidence manifests and hashes instead.

## Golden acceptance fixture

The owner-approved local reference PSD was parsed without committing the PSD.
Its visible `RESTORED` layer was exported as the full-resolution approved render
under `tests/fixtures/panther_golden/`:

- dimensions: 4500×5400;
- approved alpha bbox: `(686, 694, 3971, 5033)`;
- source PNG and approved RGBA render are stored with SHA-256 values in `manifest.json`;
- PSD provenance and required layer structure are recorded in the manifest;
- `domain/golden_acceptance.py` is a pure pixel validator;
- `tests/test_panther_golden_acceptance.py` rejects lost ears, eyes, whiskers, head foliage, lower fade, and external-edge continuity;
- `scripts/validate_panther_golden.py` validates any candidate PNG from a real job.

The old `r8` PNG is not treated as the approved reference because it is a
previous pipeline output and differs from the owner-approved PSD render.

## Evidence

```text
.venv/bin/pytest -q                         71 passed, 1 warning
python3 -m compileall -q src tests scripts  passed
node --check bridge/server.mjs              passed
git diff --check                            passed
openspec validate ... --strict              passed for both active changes
```

The full-resolution job evidence remains in the ignored
`artifacts/photopea-full-smoke-current-20261006/` directory:

- Panther 4500×5400;
- async POST → poll → core artifacts → Photopea checkpoint → reviewer accept → PSD finalize → reopen;
- `passed` with verified PSD;
- elapsed time: 265.81 seconds;
- required editable layers and exact checkpoint/reopen pixel evidence recorded;
- PSD remains outside Git.

## Model-stack smoke evidence

The deployment-only `scripts/serve_model_proposals.py` was run locally with
the real pinned weights, not a deterministic fixture:

- BiRefNet HR-matting: HTTP proposal response, 31.1 seconds at 1024 input,
  source hash and weight hash verified;
- BEN2: HTTP proposal response, 17.1 seconds at 1024 input, source hash and
  weight hash verified;
- consensus client: both independent proposal hashes verified and the service
  produced the candidate PNG/mask/previews;
- the candidate was visually inspected on navy and white backgrounds and
  rejected: the broad halo remains and owner-approved decorative perimeter
  detail/lower fade is missing;
- the service report correctly remained `review_required` with
  `visual_quality_score=0.0` and `photopea_live_api_not_configured` in the
  standalone core smoke.

An attempted external multimodal reviewer call returned HTTP 401 in the local
environment. No reviewer acceptance was fabricated and no PSD was finalized
from the rejected model candidate.

## Remaining deployment gates

These are not hidden fallbacks and must remain unchecked until external
resources exist:

1. Deploy the locally verified BiRefNet HR-matting and BEN2 adapters behind
   production resource limits, with exact model, version, license, and weights
   SHA-256 metadata.
2. Deploy SAM 2.1 protection and optional ViTMatte refinement adapters with
   their own release manifests.
3. Configure a real multimodal checkpoint reviewer at
   `VISION_REVIEW_ENDPOINT` and rerun the bounded correction loop against the
   approved Panther golden fixture.
4. Replace the deterministic smoke proposal with real model-stack evidence and
   record latency/memory measurements for the five-minute budget.

Until these resources are configured, the service is safe to run in
`review_required` mode, but it must not be presented as production automatic
matting for arbitrary artwork.

## Follow-up verification on 2026-10-07

- Fixed render-strategy dispatch so `edge_strategy=halftone`, `binary_alpha`,
  or `controlled_soft_alpha` cannot be bypassed by requesting the
  `artistic` or `conservative` variant. This prevents a continuous-alpha
  candidate from being emitted when the policy explicitly requests a
  print-safe strategy.
- Added `scripts/serve_vision_reviewer.py`, a deployment-only
  OpenAI-compatible multimodal adapter. It sends the exact artwork, mask,
  black, navy and blue-jean checkpoint bytes to a vision model and accepts
  only a high-confidence structured decision. It cannot generate scripts,
  polygons or an unbound correction mask; a rejection therefore remains
  `review_required`.
- Re-ran a full-resolution Photopea session with the corrected alpha-channel
  carrier. The result is in ignored
  `artifacts/model-acceptance-20261006/photopea-t8-session-20261007-r2/`:
  4500×5400 source, 223.34 seconds, reopened PSD, 46,538,102 bytes,
  source/checkpoint/mask/artwork hashes and all required editable layers.
- The exported navy and black previews were visually inspected. Both ears,
  eyes, whiskers and the visible foliage perimeter remain present; the outer
  background is transparent rather than a rectangular fill. The first failed
  t8 attempt used RGB luminance instead of the alpha channel and was rejected
  and not used as evidence.
- The owner golden comparator still remains the authoritative acceptance gate;
  the t8 candidate has not been promoted to production or marked as a golden
  match. The external OpenAI and Anthropic endpoints in this environment
  returned HTTP 401, so no multimodal acceptance was fabricated.

## Follow-up verification on 2026-10-07 (artifact provenance)

- Core PNG/mask/preview outputs are now marked `role: proposal` and
  `authoritative: false` in the job report.
- Photopea checkpoint exports and the PSD are marked `role: authoritative` and
  `authoritative: true`; `artifact_set.authoritative_artifacts` identifies the
  exact deliverable set and accepted revision.
- `GET /v1/jobs/{job_id}/artifacts` exposes the same provenance fields, so a
  Skill/client cannot mistake a pre-Photopea candidate for the accepted result.
- Regression and full suites passed: `73 passed`; `git diff --check` passed.
