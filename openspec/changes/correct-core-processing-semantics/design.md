# Design

## Boundary

The Skill/agent provides either:

```text
policy.json
semantic_protection_mask.png
candidate_removal_mask.png
uncertainty_mask.png
manual_corrections.png
```

The deterministic core never treats a natural-language label as a pixel mask.
If masks are absent, the service can inspect and report but must not claim a
semantically safe `passed` result.

## Domain objects

- `ResolvedMaskBundle`: frozen masks, hashes, confidence and provenance.
- `RenderPlan`: selected mode, strategy, garment models and variant renderers.
- `VariantValidation`: validation result for one named output.
- `StageStatus`: AI, Photopea, PSD, PNG and overall decisions.

## Rendering

A dispatch table maps validated modes and strategies to pure render functions.
Garment previews use explicit background and underbase approximation data.
`preview_dtg_underbase.png` is separate from `preview_white.png` and reports
threshold/spread calibration metadata.

## Service shell hardening

Read uploads in bounded chunks. Validate manifest object shape. Use an allow-list
for variants, UUID-like job IDs and path containment. Compute an idempotency
fingerprint from canonical JSON and pipeline version. Make create/find atomic
under the job store lock. Require a token for non-loopback binds.

## Photopea

The outer environment initializes Photopea once, waits for `done`, sends PNG or
mask ArrayBuffers through `postMessage`, runs the layer-building script and
retrieves PSD and exported PNG through `saveToOE`. The adapter validates a
round-trip fixture before allowing `passed`.

## Testing

Use real fixture PNGs plus approved removal/protection masks. Each fixture has
one expected status, forbidden-loss regions, halo/frame limits and garment
expectations. Add traversal, idempotency, mode dispatch, DTG non-identity and
stage-status contract tests.
