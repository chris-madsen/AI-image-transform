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
- [ ] 4.2 Implement Photopea Live PSD export adapter with source, working art, working mask and named color-fill layers; verify bridge contract and returned PSD structure.
- [x] 4.3 Implement JSON report and artifact manifest generation with hashes, warnings, validation data and pipeline version; verify report references every emitted artifact.

## 5. Async service shell

- [x] 5.1 Implement FastAPI/uvicorn endpoints for job submission, status, artifact listing/download and health; verify OpenAPI routes and HTTP error contracts.
- [ ] 5.2 Implement async executor orchestration from ingest through packaging, including mandatory Photopea PSD export and explicit bridge-unavailable review/failed states; verify POST → poll → artifacts integration test with a real Photopea export.
- [x] 5.3 Add bearer authentication, request limits, correlation/job identifiers, JSON logs and Prometheus RED/domain metrics without high-cardinality labels; verify redaction and `/metrics` smoke tests.

## 6. Skill and deployment adapters

- [x] 6.1 Update `skill/universal-image-matting/SKILL.md` with the structured policy contract, service invocation workflow, fail-closed rules and artifact interpretation; verify every documented command is executable or explicitly marked deployment-only.
- [x] 6.2 Add a Skill helper for creating policy JSON, submitting multipart jobs, polling status and downloading bundles; verify it handles review_required/refused/failed distinctly.
- [x] 6.3 Document Named Cloudflare Tunnel deployment with environment-injected URL/token and no Printify credentials; verify local service remains runnable without Cloudflare.
- [ ] 6.4 Implement and document the Photopea Live outer-environment bridge; verify real PSD structure and that core processing cannot report `passed` with a missing PSD bridge.

## 7. Verification and completion

- [ ] 7.1 Add approved source/protection/removal golden fixtures/tests for animal/text/splashes, vegetation, light internal details, typography, smoke, baked checkerboard, boundary-touching and ambiguous cases; verify exact statuses and protected-detail invariants.
- [ ] 7.2 Run full deterministic test suite, OpenSpec validation and Photopea Live API adapter/service smoke test; verify `pytest`, `openspec validate rebuild-universal-image-processing-skill --type change --strict` and local HTTP flow all pass.
- [ ] 7.3 Re-read all OpenSpec context files, mark only fully implemented checkboxes complete and produce a requirement-to-evidence summary with artifact paths; verify `openspec status --change rebuild-universal-image-processing-skill` reports all tasks complete.
