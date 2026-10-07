# Tasks

## 1. Semantic boundary

- [x] 1.1 Add frozen `ResolvedMaskBundle`, provenance and stage-status ADTs.
- [x] 1.2 Extend multipart/manifest contract with mask uploads and safe refusal for unresolved semantic text.
- [x] 1.3 Compose supplied protection/removal/uncertainty/manual masks and test protected-pixel invariants.
- [x] 1.4 Add intact-reference precedence and per-protected-region RGB/alpha diff evidence; verify a protected eye, glyph and leaf have zero changed pixels.
- [x] 1.5 Add frozen per-artwork mask tuning and fail-closed behavior when the vision decision is absent or low-confidence.

## 2. Render semantics

- [x] 2.1 Add strict variant/mode enums and a pure `RenderPlan` dispatch table.
- [x] 2.2 Implement inspect, clean-edge, baked-background, soft-fade, halftone and manual-mask behavior honestly.
- [x] 2.3 Make halftone cell size effective and validate every emitted variant separately.
- [x] 2.4 Replace the white duplicate with a distinct DTG-underbase approximation and report calibration metadata.
- [x] 2.5 Enforce external-perimeter-only cleanup as the default path; verify enclosed same-color regions and disconnected details are unchanged.

## 3. Validation and fixtures

- [x] 3.1 Add real golden source/protection/removal fixtures and exact expected outcomes.
- [x] 3.2 Add protected text/eyes/vegetation, internal-hole, boundary and dark-garment tests.
- [x] 3.3 Add per-variant validation and stage-status report contract tests.
- [x] 3.4 Add an approved manual-perimeter reference fixture; verify final alpha, navy preview and protected-pixel diff against it.

## 4. Security and service

- [x] 4.1 Add allow-listed variants, job-id validation and artifact path containment regression tests.
- [x] 4.2 Add policy-aware idempotency fingerprint, atomic conflict behavior and HTTP 409.
- [x] 4.3 Enforce public authentication, manifest shape and streaming upload limits.
- [x] 4.4 Increment HTTP metrics and remove unsupported readiness claims.
- [x] 4.5 Publish core artifacts before Photopea, keep PSD export in a bounded background executor, and make the Skill helper wait for PSD by default with an explicit `--core-only` diagnostic opt-out.

## 5. Photopea conformance

- [x] 5.1 Replace URL-embedded full-size inputs with readiness-gated ArrayBuffer messaging.
- [x] 5.2 Build one Photopea document in which Photopea authors the working mask from internal model proposal/protection evidence, with non-empty source/working-art pixels, linked raster masks and real independently toggleable garment fills; reject any caller-supplied authoritative `photopea_mask`. Verified by 8×8 revision smoke and full-resolution job-level evidence.
- [x] 5.3 Add PSD round-trip fixture and structure/visual validation; verify mask equivalence and black/navy/blue-jean rendering before allowing `passed`.
- [x] 5.4 Run a full-resolution Photopea export from the job API within the five-minute bound; verify report evidence links to the exact returned PSD and no placeholder layer is accepted. `artifacts/photopea-full-smoke-current-20261006/job-evidence.json`: Panther 4500×5400, POST→poll `passed`, verified PSD, 265.81 seconds.
- [x] 5.5 Replace the seven-PNG PSD path with a single-source Photopea authoring session that consumes only internal model proposal/protection evidence and reviewed corrections; remove `photopea_mask` from the public job/helper contract. Revisions use one live browser session and source+correction-mask ArrayBuffers, rebuilding the editable Photopea document without seven PNG inputs.
- [ ] 5.6 Wire the checkpoint/correction protocol and bounded vision review loop into the production job runtime using a concrete provider and hash-bound revisions; reject arbitrary scripts, stale revisions and polygon plans. The typed HTTP provider and live deterministic correction fixture are implemented; deployment of the external reviewer remains.
- [x] 5.7 Return retrievable checkpoint artwork, mask and black/navy/blue-jean preview bytes or authenticated URLs to the vision provider; hashes alone are not review evidence. Full job smoke downloads the authenticated checkpoint set; production vision consumption remains a provider configuration concern.
- [ ] 5.8 Implement and configure a specialized proposal stack (initial target: BiRefNet HR-matting, BEN2, SAM 2.1 protection and optional ViTMatte refinement) with pinned versions, licenses and weights hashes. BiRefNet, BEN2 and SAM 2.1 were loaded in local CPU smoke tests; SAM protection is not wired into production and the BiRefNet/BEN2 consensus failed the Panther golden visual gate.
- [x] 5.9 Add the full-resolution panther as an approved golden acceptance fixture and fail on lost ears, eyes, whiskers, head foliage, lower fade or external-edge continuity. `tests/fixtures/panther_golden/` and `tests/test_panther_golden_acceptance.py` validate the owner-approved `RESTORED` render extracted from the local reference PSD.

## 6. Evidence

- [x] 6.1 Run Python, bridge, OpenSpec and security regression suites.
- [x] 6.2 Reconcile the requirement-to-test-to-artifact evidence matrix after the corrected mask-ownership design and update only justified checkboxes. PSD binaries remain outside Git; reproducible commands, hashes and logs are recorded under ignored `artifacts/photopea-full-smoke-current-20261006/`.
