# Tasks

## 1. Foundations and domain boundaries

- [x] 1.1 Add the `printify_artwork_cleaner` package, dependency declarations and stable Makefile entrypoints; verify `uv sync --extra dev` and package import succeed.
- [x] 1.2 Add immutable domain ADTs for ProcessingPolicy, job status, inspection, mask revision, validation and artifacts; verify type-focused unit tests cover valid and invalid ingestion.
- [x] 1.3 Add `docs/domain/glossary.md`, `docs/domain/event-storming.md` and `docs/domain/context-map.md`; verify every bounded context and core event from design.md is represented.

## 2. Inspection and policy core

- [x] 2.1 Implement source freeze and RGBA inspection with sha256, alpha profile, hidden RGB statistics and crop-risk classification; verify opaque, transparent and edge-touching fixtures.
- [x] 2.2 Implement frozen ProcessingPolicy ingestion with enum, region and numeric validation; verify malformed policies return structured errors without exceptions escaping the core.
- [x] 2.3 Implement edge-connected background detection with bounded tolerance and protected-region preservation; verify internal same-color regions remain artwork.

## 3. Mask and print-safe rendering

- [x] 3.1 Implement mask revision composition and deterministic conservative/artistic candidates; verify source RGB is unchanged outside allowed alpha operations.
- [x] 3.2 Implement premultiplied-alpha resize, hidden-RGB cleanup, binary alpha and deterministic halftone rendering; verify no transparent fringe and halftone alpha is binary.
- [x] 3.3 Implement black/white/gray/navy/Blue Jean and DTG-underbase previews; verify all required preview files are generated for a fixture.
- [x] 3.4 Implement halo, frame, bounds, protected-detail and changed-pixel validation with passed/review_required/refused decisions; verify unsafe fixtures cannot become passed.

## 4. Artifact adapters

- [x] 4.1 Implement filesystem ArtifactStore and JobStore with immutable job directories, idempotency lookup and TTL cleanup; verify retry and batch isolation behavior.
- [x] 4.2 Implement Photopea Live authoring with one source, internal model proposal/protection evidence, actual source pixels, a Photopea-authored working mask, linked raster masks and real Solid Color Fill layers; verify a reopened PSD contains non-empty content, correct layer relationships and pixel equivalence. Verified by the 8×8 revision smoke and full-resolution job evidence.
- [x] 4.3 Implement JSON report and artifact manifest generation with hashes, warnings, validation data and pipeline version; verify report references every emitted artifact.

## 5. Async service shell

- [x] 5.1 Implement FastAPI/uvicorn endpoints for job submission, status, artifact listing/download and health; verify OpenAPI routes and HTTP error contracts.
- [x] 5.2 Implement async executor orchestration including mandatory Photopea pixel evidence, same-revision protected-pixel evidence and explicit bridge-unavailable states; verify POST → poll → PNG/mask/PSD artifacts with a real Photopea export. Fresh full-resolution job evidence completed in 290.60 seconds; the deterministic proposal remains a failed owner-golden candidate.
- [x] 5.3 Add bearer authentication, request limits, correlation/job identifiers, JSON logs and Prometheus RED/domain metrics without high-cardinality labels; verify redaction and `/metrics` smoke tests.

## 6. Skill and deployment adapters

- [x] 6.1 Update `skill/universal-image-matting/SKILL.md` with the structured policy contract, service invocation workflow, fail-closed rules and artifact interpretation; verify every documented command is executable or explicitly marked deployment-only.
- [x] 6.2 Remove caller-supplied final-mask arguments from the Skill helper, submit source/intent only, poll the mandatory Photopea authoring/review stage by default and download bundles; verify it handles review_required/refused/failed distinctly.
- [x] 6.3 Document Named Cloudflare Tunnel deployment with environment-injected URL/token and no Printify credentials; verify local service remains runnable without Cloudflare.
- [x] 6.4 Implement and document the production Photopea Live outer-environment workflow; verify ArrayBuffer transfer of internal proposals/corrections, Photopea mask authoring, reviewable checkpoints, PSD reopen/pixel inspection and no `passed` status without a typed review decision and conformance evidence. A configured external vision credential/model remains an operational prerequisite for live automatic acceptance.
- [x] 6.5 Implement the Windows native ONNX Runtime DirectML proposal adapter for the Vega 56 deployment: pinned DirectML environment, DML-first/CPU-second provider selection, sequential single-request inference, fixed 1024/2048 benchmark, LAN server and firewall scripts, model metadata and fail-closed hash checks. A physical Windows GPU run remains deployment evidence and is not claimed from Linux.

## 7. Verification and completion

- [x] 7.1 Add deterministic contract golden fixtures for animal/text/splashes, vegetation, light internal details, typography, smoke, baked checkerboard, boundary-touching and ambiguous cases; verify zero protected-pixel loss and expected status per fixture. The owner-approved Panther reference remains the separate production-quality golden.
- [x] 7.2 Add a manual-perimeter reference fixture and a strict candidate comparator. The owner-approved Panther render and alpha are checked by `tests/test_panther_golden_acceptance.py`; the current deterministic proposal is intentionally rejected by that comparator, while PSD structure is independently verified by Photopea round-trip evidence.
- [x] 7.3 Run full deterministic, Photopea round-trip and HTTP integration suites; verify `pytest`, both strict OpenSpec validations and the local POST → poll flow pass.
- [x] 7.4 Re-read all OpenSpec and DDD context files, mark only evidenced tasks complete and produce a requirement-to-test-to-artifact summary; verify no formal PSD-only success remains.
- [x] 7.5 Implement at least one pinned specialized matting provider and a second independent proposal path; record model/version/license/weights hashes and run the Panther acceptance fixture. BiRefNet/BEN2 and the SAM2 protection adapter are implemented and pinned evidence is recorded; the candidate failed Panther acceptance and remains unpromoted.
- [ ] 7.6 Promote the specialized proposal stack only after the Panther golden fixture passes with a real external visual-review decision and recorded latency/memory evidence.
