# Proposal

## Why

The product needs a deterministic, domain-first artwork-cleaning service rather
than benchmark orchestration. A valid PSD container is not a valid print-ready
result: the system must prove that its alpha mask preserves protected artwork,
removes only approved external perimeter contamination, and remains editable in
Photopea.

## What Changes

- **BREAKING**: replace the benchmark-first entrypoint with a domain-first
  asynchronous artwork-processing service.
- Freeze structured user intent, source bytes and mask revisions before rendering.
- Enforce manual-equivalent external-perimeter cleanup: remove only approved
  edge-connected pixels and give protected reference pixels precedence.
- Produce PNG variants, previews, report metadata and a semantically editable
  PSD through Photopea Live API.
- Require PSD-content, mask-equivalence and dark-garment visual proof before a
  job can become `passed`.
- Keep GPT outside the service as an intent interpreter; require pixel masks for
  semantic protection.
- Exclude Printify upload, store integrations, MCP, mouse automation and Python
  PSD writers from the core.

## Capabilities

### New Capabilities

- `agent-job-contract`: asynchronous jobs, idempotency, lifecycle and artifacts.
- `artwork-inspection`: immutable source facts and boundary-risk classification.
- `semantic-policy-and-protection`: frozen intent and pixel-level protection.
- `mask-composition`: immutable perimeter, protection and correction mask revisions.
- `print-safe-rendering`: alpha-only variants and garment previews.
- `review-and-validation`: print, protection and acceptance decisions.
- `artifact-export`: immutable bundles and evidence reports.
- `photopea-adapter`: Photopea Live API PSD construction and conformance proof.

### Modified Capabilities

- None. Canonical specs will be materialized when this active change is archived.

## Impact

The change affects the FastAPI service, Skill contract, artifact bundle, Photopea
outer environment, domain model, tests and local deployment documentation. It
adds no Printify credentials or hosted model dependency.
