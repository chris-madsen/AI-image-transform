# Design

## Context

The product is a local image-processing service invoked by a ChatGPT Skill.
GPT converts user language into a validated `ProcessingPolicy`; the service
executes deterministic image operations and returns immutable artifacts.

## Architecture

```text
ChatGPT / GPT
  -> structured ProcessingPolicy
Skill adapter
  -> HTTPS / Named Cloudflare Tunnel
FastAPI image service
  -> domain pipeline
PNG, masks, previews, report
  -> PhotopeaLiveApiAdapter
Photopea Live API -> layered PSD
```

The functional core contains domain ADTs and pure image rules. The imperative
shell owns HTTP, filesystem, clock, job execution and external adapters.

## Bounded contexts

1. **Agent Job** — `ProcessingJob`, idempotency and lifecycle.
2. **Artwork Inspection** — geometry, alpha profile, edge classification and inspection report.
3. **Semantic Policy** — frozen policy and protected intent.
4. **Mask Composition** — AI/vision mask, edge background, protection and revisions.
5. **Print-safe Rendering** — conservative/artistic alpha variants and previews.
6. **Review and Validation** — halo, frame, detail, bounds and decision status.
7. **Artifact Packaging** — immutable files, hashes and JSON report.
8. **Photopea Integration** — Photopea Live API outer environment and PSD export.

## Pipeline

```text
Ingest -> freeze source/policy -> inspect -> compose mask -> render variants
-> generate previews -> validate -> export artifacts -> complete job
```

A missing or unavailable mandatory Photopea adapter forces `review_required` or
`failed`. It cannot be hidden by a fallback writer.

## Ports

- `VisionProvider`
- `ArtifactStore`
- `JobStore`
- `PsdExporter`
- `PreviewRenderer`
- `Clock`
- `PhotopeaLiveApiAdapter`

Domain code MUST NOT call filesystem, network, time or model APIs directly.

## Photopea PSD export

The service sends candidate PNGs and a mask to an outer browser environment.
That environment embeds Photopea in an iframe, communicates through Web
Messaging, runs a layer-building script and requests
`app.activeDocument.saveToOE("psd:true")`. The returned bytes are stored as the
PSD artifact. The bridge folder is infrastructure only; the public abstraction
is `PhotopeaLiveApiAdapter`.

A local Python PSD writer such as `psd-tools` or `pytoshop` is deliberately not
used because the required document behavior must be produced by Photopea.

## Security and operations

Use bearer authentication, HTTPS through a Named Cloudflare Tunnel, temporary
local storage and TTL cleanup. No Printify credentials are accepted. Logs are
structured JSON and must not contain source bytes or bearer tokens.
