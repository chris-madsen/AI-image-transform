# Tasks

## 1. Semantic boundary

- [x] 1.1 Add frozen `ResolvedMaskBundle`, provenance and stage-status ADTs.
- [x] 1.2 Extend multipart/manifest contract with mask uploads and safe refusal for unresolved semantic text.
- [x] 1.3 Compose supplied protection/removal/uncertainty/manual masks and test protected-pixel invariants.

## 2. Render semantics

- [x] 2.1 Add strict variant/mode enums and a pure `RenderPlan` dispatch table.
- [x] 2.2 Implement inspect, clean-edge, baked-background, soft-fade, halftone and manual-mask behavior honestly.
- [x] 2.3 Make halftone cell size effective and validate every emitted variant separately.
- [x] 2.4 Replace the white duplicate with a distinct DTG-underbase approximation and report calibration metadata.

## 3. Validation and fixtures

- [ ] 3.1 Add real golden source/protection/removal fixtures and exact expected outcomes.
- [ ] 3.2 Add protected text/eyes/vegetation, internal-hole, boundary and dark-garment tests.
- [x] 3.3 Add per-variant validation and stage-status report contract tests.

## 4. Security and service

- [x] 4.1 Add allow-listed variants, job-id validation and artifact path containment regression tests.
- [x] 4.2 Add policy-aware idempotency fingerprint, atomic conflict behavior and HTTP 409.
- [x] 4.3 Enforce public authentication, manifest shape and streaming upload limits.
- [x] 4.4 Increment HTTP metrics and remove unsupported readiness claims.

## 5. Photopea

- [x] 5.1 Replace URL-embedded full-size inputs with readiness-gated ArrayBuffer messaging.
- [ ] 5.2 Build real raster-mask and color-fill layer script from request metadata.
- [ ] 5.3 Add PSD round-trip fixture and structure validation; keep task incomplete until a real Photopea run passes.

## 6. Evidence

- [x] 6.1 Run Python, bridge, OpenSpec and security regression suites.
- [ ] 6.2 Produce requirement-to-test-to-artifact evidence and update only justified checkboxes.
