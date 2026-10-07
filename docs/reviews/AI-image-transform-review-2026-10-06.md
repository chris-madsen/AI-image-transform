# AI Image Transform / Photopea Pipeline Review

**Date:** 2026-10-06
**Scope:** Follow-up audit after the Photopea raster-mask and production-runtime corrections.
**Decision:** Core correction work is verified; deployment-dependent model and reviewer stages remain explicitly incomplete.

## Verified corrections

- `photopea_mask` and `photopea_mask_revision` are not public job inputs.
- Photopea receives one source ArrayBuffer plus two internal initial grayscale carriers (accepted/restored and conservative/gaps); revisions receive one correction carrier. The primary path no longer imports seven full-size PNG documents, polygon plans, or arbitrary scripts.
- The Photopea bridge authors the working mask, linked raster masks, source backup, restored/gap layers, and independently toggleable black/navy/blue-jean fills.
- The service keeps one outer Photopea browser session and one Photopea document through the bounded review loop. Revisions add a new accepted raster-mask layer inside that document and preserve the source, gap layer and editable fill layers until finalization.
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

The previous full-resolution job evidence remains in the ignored
`artifacts/photopea-full-smoke-current-20261006/` directory and predates the
current HMAC finalization contract. It must not be used as proof for the
current bridge without rerunning the command below.

- Panther 4500×5400;
- async POST → poll → core artifacts → Photopea checkpoint → reviewer accept → PSD finalize → reopen;
- `passed` with verified PSD under the old contract;
- elapsed time: 265.81 seconds (historical);
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

## Follow-up verification on 2026-10-07 (remaining implementation gates)

- Added a typed, source-bound `SAM21ProtectionProvider` and the deployment-only
  `scripts/serve_sam2_protection.py`. SAM2 returns protection/uncertainty only;
  border-touching masks are excluded and no SAM alpha becomes authoritative.
- Wired optional SAM2 protection into the BiRefNet/BEN2 consensus behind
  explicit endpoint/version/license/weights-hash configuration. Missing or
  mismatched pins fail closed.
- Added the eight deterministic contract fixture classes required by the
  acceptance matrix: animal/text/splashes, vegetation, light internal details,
  typography, smoke, baked checkerboard, boundary-touching and ambiguous.
  Their PNG hashes, protected-pixel invariants and review-required statuses are
  tested in `tests/test_golden_fixture_classes.py`.
- The implementation tasks are now complete in both OpenSpec changes. Two
  intentionally separate promotion tasks remain: the real external reviewer
  must accept the Photopea checkpoint and the Panther candidate must pass the
  owner-approved golden. The current external credentials return HTTP 401 and
  the current BiRefNet/BEN2 candidate remains rejected; neither condition is
  hidden or downgraded.
- Verification: `77 passed`, `compileall`, `node --check bridge/server.mjs`,
  both OpenSpec strict validations and `git diff --check` passed.

## Follow-up verification on 2026-10-07 (current review correction)

- Rejected the public one-shot Photopea export path. PSD finalization now uses
  only the reviewed session endpoint and requires an HMAC acceptance token bound
  to source hash, revision id and the current checkpoint hash.
- Initial sessions now transfer source plus separate accepted/restored and
  conservative/gaps carriers. Revision transfer sends only a correction mask;
  the source document is not resent or closed between revisions.
- Checkpoints expose authenticated source, artwork, mask and red-contour
  overlay bytes to the reviewer. The reviewer adapter now requires all of
  those pixels plus black, navy and blue-jean previews.
- Added deterministic edge-band chroma, contour-distance and dark-garment
  partial-alpha metrics to the validation report. These metrics are safety
  signals; the owner-approved Panther golden remains the authoritative visual
  comparator.
- Fixed final PSD visibility restoration. Before `saveToOE("psd:true")`, the
  bridge explicitly makes the accepted `RESTORED*` layer visible; round-trip
  preview scripts can no longer leave the saved document visually empty.
- A fresh real 4500×5400 POST→poll→Photopea→review→HMAC-finalize smoke passed
  in 290.60 seconds with reopened pixel evidence and the required editable
  layers. The authoritative checkpoint PNG was visually inspected and contains
  the subject, ears, eyes, whiskers and foliage. The owner-approved Panther
  golden comparison of this deterministic proposal fixture failed (external
  edge loss 26714 pixels; lower-fade MAE 40.14), so specialized-model
  promotion remains blocked and this candidate must not be represented as the
  approved Panther result.
- The smoke PSD is intentionally not committed. The authoritative PNGs,
  masks, previews and PSD are produced by the same accepted Photopea revision;
  the owner golden gate still requires a real deployed model/reviewer result.

## Follow-up verification on 2026-10-07 (Windows DirectML deployment)

- Added a native Windows ONNX Runtime adapter for the Radeon RX Vega 56 in
  `scripts/serve_onnx_proposals.py`. It uses `DmlExecutionProvider` before an
  explicitly available `CPUExecutionProvider`, one sequential inference at a
  time, disabled memory-pattern allocation, fixed 1024/2048 input sizes,
  source-bound alpha resizing and model/weights SHA-256 metadata.
- Added reproducible Windows setup, server, firewall and batch-one benchmark
  scripts under `deployment/windows/`. The setup requires
  `onnxruntime-directml==1.20.1`; it does not use ROCm, WSL2, weight download
  or a paid API. CPU fallback is available only as an explicit diagnostic
  switch and is not silent.
- Added contract tests for provider ordering, required-DirectML refusal,
  preprocessing, logits-to-alpha conversion and unsupported-provider refusal.
  The adapter is intentionally lazy-imported so the Linux core test suite does
  not need a Windows-only runtime package.
- Added the 1024/2048 benchmark contract. A fixed-size ONNX export must reject
  a different geometry; the 4500x5400 artwork is resized inside the adapter and
  its alpha is resized back before the local deterministic pipeline continues.
- Windows GPU execution is not claimed as completed here: this environment is
  Linux and has no `pwsh` or Vega 56 DirectML runtime. The setup script performs
  the provider check on the actual Windows host; its benchmark output and
  latency/memory measurements are required before deployment evidence can be
  considered complete. This does not change the separate Panther golden gate:
  the current specialized proposal remains rejected and unpromoted.
