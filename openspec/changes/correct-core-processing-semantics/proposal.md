# Proposal

## Why

The first implementation made the service appear safer and more complete than
it was. It could return a valid PSD container with empty working layers and did
not yet guarantee automatic manual-equivalent perimeter masking or protected
pixel preservation.

## What Changes

- Require resolved pixel masks for semantic intent and fail closed without them.
- Define manual-equivalent external-perimeter cleanup and intact-reference
  precedence as observable behavior.
- Make every variant and dark-garment preview independently validated.
- Require Photopea PSD conformance: real layer pixels, linked mask, real fills,
  structure evidence and visual proof.
- Preserve service security, idempotency and explicit stage status.
- Add approved golden references and requirement-to-evidence traceability.

## Non-goals

This change does not add a hosted model, Printify credentials, Etsy, MCP, a
local Python PSD writer or generative repainting.
