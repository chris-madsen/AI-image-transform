# Proposal

## Why

The first implementation established service infrastructure but overstated
semantic safety. Text such as `must_keep: ["eyes", "text"]` does not create a
pixel protection mask, requested modes and garments do not consistently select
algorithms, the DTG preview is only a white composite, and artifact paths and
idempotency are not fully hardened. The Photopea adapter also does not yet
prove the required editable PSD structure.

## What Changes

- Make the AI/agent-to-core boundary explicit with supplied pixel masks and a
  `ResolvedMaskBundle`.
- Return `review_required` when semantic text cannot be resolved into pixels.
- Build an explicit `RenderPlan` from mode, edge strategy, garments, inspection
  and uncertainty; apply and validate every requested variant independently.
- Implement honest dark-garment/DTG-underbase approximation and report its limits.
- Harden paths, job IDs, policy-aware idempotency, manifest validation,
  upload limits and public authentication.
- Split stage diagnostics into AI mask, Photopea processing, PSD validation,
  PNG validation and overall status.
- Add real golden fixtures with exact expected statuses and protected regions.
- Make Photopea Live API export create and validate the promised editable PSD
  structure. A full PSD round-trip remains a blocking acceptance item.

## Non-goals

This change does not add a hosted AI model, Printify API credentials, Etsy,
MCP, GitHub Actions or a local Python PSD writer.
