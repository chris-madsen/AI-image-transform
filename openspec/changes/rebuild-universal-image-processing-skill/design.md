# Design

## Context

The service receives immutable source bytes and a frozen `ProcessingPolicy` from
a Skill. It must remove only approved external perimeter pixels, preserve the
visible source artwork, and return a Photopea-editable PSD. See `proposal.md`
for the product motivation.

## Goals / Non-Goals

**Goals:**

- Keep the functional core deterministic and free of filesystem, network, time
  and model calls.
- Model job lifecycle, mask revisions and acceptance decisions explicitly.
- Construct and prove a real Photopea document, not a PSD-format placeholder.
- Preserve protected pixels while allowing reviewed external-background removal.

**Non-Goals:**

- Generative reconstruction, Printify upload, hosted queues, a local Python PSD
  writer, or Photopea mouse automation.

## Decisions

### DDD boundaries and aggregates

`ProcessingJob` is the aggregate root for one frozen source, policy, requested
outputs and lifecycle. It owns terminal status and references immutable
`MaskRevision` and `ArtifactBundle` values. `MaskRevision` is immutable and
carries parent identity, hashes, provenance, confidence, protection and removal
pixels. `ArtifactBundle` is immutable after packaging.

The bounded contexts are Agent Job, Artwork Inspection, Semantic Policy,
Mask Composition, Print-safe Rendering, Review & Validation and Artifact
Packaging. Photopea is an external system, isolated behind the `PsdExporter`
port and `PhotopeaLiveApiAdapter` anti-corruption layer; Photopea types and
browser messaging do not enter the domain core.

### Manual-equivalent perimeter mask

The core derives removal only from approved edge-connected pixels. Semantic
labels never become pixels by inference inside the service. A supplied protected
reference or protection mask takes precedence over removal. Enclosed regions,
internal highlights and disconnected artwork remain unchanged unless an explicit
reviewed mask permits a change.

### PSD as a semantic artifact

The Photopea adapter transfers one source and two internal grayscale/alpha mask carriers
into one document. It creates non-empty `SOURCE BACKUP`, `RESTORED`, `WITH
GAPS`, `WORKING MASK` and editable Solid Color Fill layers, then links the
carrier-derived raster mask to both artwork layers. The adapter proves layer
content, mask equivalence and rendered dark-garment behavior after reopening
the exact returned PSD. `8BPS` is a transport sanity check only.

### Functional core and imperative shell

Pure functions freeze policies, inspect pixels, compose masks, render candidates
and calculate validation facts. Ports handle VisionProvider, JobStore,
ArtifactStore, PsdExporter, PreviewRenderer and Clock. HTTP, filesystem,
Photopea browser execution and tunnel configuration remain adapters.

## Risks / Trade-offs

- [Low-confidence boundary] → return `review_required`; never expand removal.
- [Photopea protocol or structure failure] → retain PNG/report evidence but do
  not return `passed`.
- [Large PSD latency] → use ArrayBuffer messaging, bounded timeouts and explicit
  terminal diagnostics rather than a fallback writer.
- [Semantic ambiguity] → require pixel-level masks from the Skill or approved
  vision provider.

## Migration Plan

1. Preserve source and existing output artifacts for audit.
2. Add pixel-mask and PSD-conformance contracts before changing rendering.
3. Implement the Photopea adapter behind the existing `PsdExporter` port.
4. Run approved golden and Photopea round-trip fixtures.
5. Permit `passed` only after all mandatory evidence is available.
