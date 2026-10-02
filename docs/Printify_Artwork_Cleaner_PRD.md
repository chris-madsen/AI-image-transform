# Printify Artwork Cleaner — Product Requirements Document

**Status:** Draft for implementation
**Version:** 1.0
**Date:** 2026-10-02
**Product owner:** Zoya

## 1. Product summary

Printify Artwork Cleaner prepares raster artwork for apparel printing. It
removes confirmed external backgrounds, frames, halos and defective edge pixels
while preserving the original visible design, readable text, thin details and
organic silhouettes.

The product is print-oriented rather than preview-oriented. Validation MUST
consider dark garments, partial alpha, DTG underbase behavior and the risk of
white or colored fringes. It must support animals, people, plants, typography,
vintage graphics, splashes, smoke, watercolor and mixed compositions.

GPT interprets the user's natural-language intent. The local service executes a
frozen structured policy. GPT is not called by the service and the service does
not perform generative redraw.

## 2. Goals

- Preserve source RGB and modify alpha/masks deliberately.
- Detect and remove only confirmed edge-connected background.
- Preserve protected semantic details and internal light regions.
- Produce conservative and artistic variants with print previews.
- Produce an editable PSD through the Photopea Live API.
- Expose an asynchronous, authenticated, idempotent HTTP job contract.
- Fail closed when policy, validation or PSD export is ambiguous/unavailable.
- Keep the core independent from Printify, Etsy, MCP and store credentials.

## 3. Non-goals

- Printify upload or catalog management.
- Etsy or store integration.
- ChatGPT Business or MCP as a runtime dependency.
- Mouse-coordinate automation of Photopea.
- A Python PSD writer.
- Automatic generative repainting of artwork.

## 4. Users and workflow

1. A user submits artwork and describes what must remain and what may be removed.
2. GPT converts the request into a validated `ProcessingPolicy`.
3. The Skill submits source, manifest and policy to the local service.
4. The service accepts a job and returns a polling URL.
5. The pipeline freezes input, inspects artwork, composes masks and renders candidates.
6. The service creates previews, validates candidates and requests PSD export from Photopea.
7. The Skill downloads the immutable artifact bundle and reports `passed`,
   `review_required`, `refused` or `failed` honestly.

## 5. Structured policy

```json
{
  "primary_subject": "main illustrated subject",
  "must_keep": ["all readable text", "face and thin details"],
  "keep_if_intentional": ["plants, smoke and splashes crossing the subject"],
  "remove_only": ["external flat background and confirmed edge debris"],
  "target_garments": ["black", "navy", "blue_jean", "white"],
  "edge_strategy": "auto_print_safe",
  "requested_variants": ["conservative", "artistic"]
}
```

The policy is frozen at ingestion. Invalid or ambiguous policy MUST produce
`review_required`; the service MUST NOT invent a fallback interpretation.

## 6. Bounded contexts

### Agent Job

Owns `ProcessingJob`, idempotency, lifecycle, polling and artifact discovery.

### Artwork Inspection

Owns source geometry, color mode, alpha profile, hidden RGB and edge
classification. It identifies crop risk and baked backgrounds.

### Semantic Policy and Protection

Owns the frozen policy, protected regions and the boundary between user intent
and image algorithms.

### Mask Composition

Combines vision/AI masks, edge-connected background, protected regions, local
corrections, holes and uncertainty into immutable `MaskRevision` values.

### Print-safe Rendering

Creates binary-alpha, controlled-soft-alpha, halftone, conservative and
artistic candidates. It uses premultiplied alpha for resizing and never changes
source RGB without an explicit rule.

### Review and Validation

Calculates halo/frame scores, protected-detail checks, bounds, resolution,
new transparent holes and DTG-underbase previews. It returns `Passed`,
`ReviewRequired` or `Refused`.

### Artifact Packaging

Creates immutable files, hashes, report metadata and the Photopea PSD artifact.

### Photopea Live API

The `PhotopeaLiveApiAdapter` sends image data to an outer environment that
embeds Photopea, runs layer scripts through Live Messaging and retrieves the PSD
with `app.activeDocument.saveToOE("psd:true")`.

## 7. Processing pipeline

```text
Ingest
→ freeze source and policy
→ inspect artwork
→ build protected mask
→ compose candidate mask
→ render conservative/artistic variants
→ generate print previews
→ validate
→ export PNG/mask/PSD/report
→ complete job
```

A review pipeline may accept a new policy or mask revision, re-render candidates
and re-run validation. Batch processing uses an independent job, report and
status per image; one failure MUST NOT cancel other jobs.

## 8. HTTP API

```http
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/artifacts
GET  /v1/artifacts/{job_id}/{artifact_name}
```

`POST /v1/jobs` accepts multipart source image, JSON manifest, structured policy
and optional idempotency/correlation keys. The response is:

```json
{
  "job_id": "...",
  "status": "accepted",
  "poll_url": "/v1/jobs/..."
}
```

The service uses bearer authentication, HTTPS transport, temporary local
storage and TTL cleanup. Printify credentials MUST never be accepted.

## 9. Artifact bundle

The bundle includes:

```text
artwork_conservative.png
artwork_artistic.png
mask_conservative.png
alpha_mask.png
preview_black.png
preview_white.png
preview_gray.png
preview_navy.png
preview_blue_jean.png
preview_dtg_underbase.png
artwork_editable.psd
report.json
```

The PSD MUST contain `SOURCE BACKUP`, `WORKING ART`, `WORKING MASK` and print
test layers. It MUST be generated by Photopea Live API, not by a Python PSD
library. Without the Photopea adapter the job cannot be `passed`.

## 10. Report

`report.json` MUST include job status, source dimensions, source hash, pipeline
version, selected strategy, alpha statistics, changed-pixel count, halo/frame
scores, protected-detail checks, warnings, review regions and artifact hashes.

## 11. Quality and safety rules

- Hidden RGB under alpha zero is canonicalized safely.
- Premultiplied resize MUST NOT create a fringe.
- Internal light details MUST NOT be classified as external background.
- Protected regions MUST survive mask composition.
- Halftone alpha contains only `0` and `255`.
- Continuous alpha with visible glow cannot pass validation.
- Missing model, dependency, policy or Photopea adapter is an explicit error or review state.
- The original source file is never overwritten.

## 12. Acceptance criteria

The MVP is accepted when:

- OpenSpec proposal, specs, design and tasks validate.
- The Skill creates and submits structured policy.
- The service accepts asynchronous jobs and supports polling/idempotency.
- Inspection, mask composition, rendering, previews and validation work.
- PNG, masks, previews, PSD and JSON report are produced when Photopea is available.
- Ambiguous cases become `review_required` or `refused`.
- Golden tests preserve protected details.
- The product has no mandatory Printify, MCP, Etsy or ChatGPT runtime dependency.
- Photopea can open the produced PSD and continue manual editing.
