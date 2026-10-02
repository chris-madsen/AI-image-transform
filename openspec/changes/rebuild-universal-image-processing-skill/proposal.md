# Proposal

## Why

The previous repository was benchmark-first code, not a product domain model. It
lacked a frozen policy, job lifecycle, safe refusal states, review status and a
stable artifact contract. The product needs a domain-first service that accepts
structured intent from the Skill and processes artwork without regenerating the
source RGB.

## What Changes

- **BREAKING**: replace the benchmark-first entrypoint with a domain-first artwork pipeline.
- Add frozen `ProcessingPolicy`, inspection, protected regions and explicit job states.
- Add an asynchronous job API with idempotency, polling and artifact discovery.
- Implement inspection, edge-connected masking, alpha rendering, previews and validation.
- Forbid generative redraw, hidden fallbacks and source overwrites.
- Export PNG, masks, print previews, JSON report and PSD through the Photopea Live API.
- Add structured events, correlation identifiers and RED/domain metrics.
- Keep GPT as the user-intent interpreter on the Skill side; the service accepts only validated policy.
- Use `PhotopeaLiveApiAdapter` for PSD export. Missing Photopea access MUST produce
  `review_required` or `failed`, never a false `passed` result.
- Exclude Printify upload, Etsy/store workflows, MCP and mouse automation from the core.

## Capabilities

- `agent-job-contract`: asynchronous jobs, idempotency, lifecycle and artifact discovery.
- `artwork-inspection`: source normalization, alpha/RGB inspection and crop-risk detection.
- `semantic-policy-and-protection`: frozen policy and protected semantic regions.
- `mask-composition`: mask revisions, edge connectivity and uncertainty.
- `print-safe-rendering`: alpha-only rendering, premultiplied resize and DTG previews.
- `review-and-validation`: halo, frame, detail and acceptance checks.
- `artifact-export`: immutable bundle, report and Photopea-exported layered PSD.
- `photopea-adapter`: outer environment for Photopea Live Messaging.

## Non-goals

This change does not add Printify credentials, cloud storage, a hosted queue,
a Photopea mouse automation workflow or a local Python PSD writer.
