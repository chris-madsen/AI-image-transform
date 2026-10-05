# Design

## Context

The current service has a valid job shell and deterministic rendering core, but
its PSD bridge can create named placeholders instead of an editable composition.
The correction implements the behavioral contracts described by the updated PRD
and base change.

## Goals / Non-Goals

**Goals:** prove manual-equivalent perimeter cleanup, semantic protection,
per-variant validation and real Photopea PSD conformance.

**Non-Goals:** change source RGB, add a generative model, or introduce a Python
PSD writer.

## Decisions

### Evidence-first mask composition

The core receives a frozen `ResolvedMaskBundle`; text labels are insufficient.
Default removal is edge-connected and protection pixels win. A protection diff
is calculated against the frozen source/reference for every candidate.

### One Photopea document and iterative mask session

Photopea is the source of truth for mask authoring. The bridge opens the source
once, transfers one grayscale/alpha mask carrier through ArrayBuffer messaging,
and uses the carrier transparency with the canonical charID Action Manager
sequence to create linked raster masks. It does not approximate fur, whiskers,
smoke or typography with polygons and does not import seven Python-generated
artwork/mask PNG documents. The resulting raster masks, working mask and
editable Solid Color Fill layers are created in Photopea and saved through
`saveToOE("psd:true")`.

The Skill/vision adapter owns a bounded review loop. After each Photopea
checkpoint it requests a vision assessment of the rendered artwork and mask
preview. The assessment returns a hash-bound `RasterMaskRevision` plus a mask
carrier, never arbitrary JavaScript. The bridge applies that revision to the
same Photopea document and emits the next checkpoint. The loop is capped by
revision count and wall-clock budget; missing, stale or weak vision evidence
remains `review_required`.

### Acceptance state machine

PNG validation and PSD conformance are separate stage statuses. `passed` is
reachable only when every required variant, protected-pixel check, preview check
and PSD proof succeeds. Missing evidence maps to `review_required` or `failed`.

### Bounded Photopea execution

The core job writes PNGs, masks and previews before scheduling Photopea in a
separate PSD executor. The job remains `running` with
`psd_export_status=pending` and later publishes `verified`, `unverified` or
`failed`. The bridge timeout is five minutes. A diagnostic structure-only
export is never promoted to `passed`.

## Risks / Trade-offs

- [Boundary ambiguity] → preserve pixels and request review.
- [Photopea scripting incompatibility] → fail conformance rather than synthesize
  a PSD.
- [Full-resolution export latency] → bounded async job timeout and explicit
  diagnostics; no fallback writer.

## Migration Plan

1. Add conformance fixtures before changing completion status.
2. Build the actual Photopea layer/mask document.
3. Reopen or inspect and render the returned PSD.
4. Run golden reference and HTTP end-to-end tests.
5. Mark only evidenced tasks complete.
