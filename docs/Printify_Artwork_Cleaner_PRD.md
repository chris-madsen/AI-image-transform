# Printify Artwork Cleaner — Product Requirements Document

**Status:** Draft for implementation; PSD and perimeter-mask acceptance criteria tightened
**Version:** 1.1
**Date:** 2026-10-03
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
- Produce an automatic mask that is equivalent to approved manual
  external-perimeter cleanup: it removes only edge-connected contamination and
  never substitutes, redraws, or weakens preserved artwork.
- Produce conservative and artistic variants with print previews.
- Produce an editable PSD through the Photopea Live API.
- Make every promised PSD layer contain the corresponding real pixel data and
  validate its Photopea rendering, not merely its name or PSD file signature.
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

The policy contains a per-artwork `mask_tuning` decision selected by the
vision/agent boundary. It is recalculated for every source or mask revision;
repository defaults are only compatibility values and can never authorize a
passed job. The agent inspects emitted candidate previews before accepting or
submitting the next revision.

## 5. Structured policy

```json
{
  "primary_subject": "main illustrated subject",
  "must_keep": ["all readable text", "face and thin details"],
  "keep_if_intentional": ["plants, smoke and splashes crossing the subject"],
  "remove_only": ["external flat background and confirmed edge debris"],
  "target_garments": ["black", "navy", "blue_jean", "white"],
  "edge_strategy": "auto_print_safe",
  "requested_variants": ["conservative", "artistic"],
  "mask_tuning": {
    "decision_id": "vision-review-source-hash-r1",
    "background_tolerance": 8,
    "fade_low_distance": 4,
    "fade_full_distance": 64,
    "fade_band_radius": 4,
    "confidence": 0.91
  },
  "visual_quality": {
    "reference_id": "named-golden-or-review-rubric",
    "overall_score": 0.0,
    "subject_integrity": 0.0,
    "intentional_detail_score": 0.0,
    "edge_naturalness": 0.0,
    "artifact_free_score": 0.0,
    "confidence": 0.0,
    "reviewer_notes": []
  },
  "photopea_mask_plan": {
    "revision_id": "vision-mask-source-hash-r1",
    "subject_polygons": [[[0.10, 0.10], [0.90, 0.10], [0.90, 0.90], [0.10, 0.90]]],
    "remove_polygons": [],
    "protect_polygons": [],
    "feather_px": 2,
    "confidence": 0.92
  }
}
```

The policy is frozen at ingestion. Invalid or ambiguous policy MUST produce
`review_required`; the service MUST NOT invent a fallback interpretation.
The visual-quality fields are supplied by GPT/vision at the agent boundary;
the service does not hallucinate them. Missing assessment, low confidence or a
low score is a review decision, not permission to export a finished print.
`photopea_mask_plan` is a frozen, per-artwork vision decision. It contains
normalized polygon corrections only; it is not JavaScript and it is not a
pre-rendered mask upload. Each checkpoint correction creates a new
`revision_id`. If the plan is missing or ambiguous, the PSD stage must fail
closed or remain `review_required`.

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

The agent MUST also provide a frozen visual-quality assessment. A valid alpha
channel or PSD container is not evidence that the artwork is visually suitable:
the assessment covers subject integrity, intentional decorative details,
natural edge shape, isolated debris and confidence against a named reference
or review rubric. Missing or weak assessment evidence produces
`review_required`.

The default safe behavior is **manual-equivalent external-perimeter cleanup**:
the service starts from the canvas border, identifies only removable
edge-connected pixels, and applies the resulting alpha change outside protected
artwork. It MUST NOT use a whole-image color key, flood-fill enclosed regions,
or use a semantic label as a substitute for a pixel mask. When an intact
reference and a perimeter-clean candidate are provided, protected pixels from
the intact reference win over removal pixels from the candidate.

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

The adapter constructs one editable document. It is not sufficient to open
separate documents, rename them, or create empty placeholder layers.
The intended session is `source → typed mask plan → Photopea checkpoint →
vision review → typed correction → checkpoint` within the same document. The
bridge must reject script/runtime errors promptly; it must never silently fall
back to importing seven generated PNG documents.

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

The default cleanup path is:

```text
immutable source with intact details
→ external-perimeter removal proposal
→ protected-pixel precedence
→ final alpha mask
→ PNG candidate and Photopea layer mask
```

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

The PSD MUST be generated by the Photopea Live API, not by a Python PSD library.
Without the Photopea adapter the job cannot be `passed`. It MUST be one
Photopea document with the following non-placeholder structure:

- `SOURCE BACKUP`: a pixel layer containing the unmodified frozen source.
- `RESTORED`: a pixel layer containing the artistic/reference-preserving candidate
  RGB, with its linked raster mask visible by default.
- `WITH GAPS`: a separate pixel layer containing the conservative candidate and
  its own linked raster mask; it is independently toggleable and hidden by
  default.
- `WORKING MASK`: a grayscale pixel layer containing the exact final alpha mask.
- Raster layer masks linked to `RESTORED` and `WITH GAPS`; neither candidate is
  flattened into the other.
- Black, white, gray, navy and blue-jean preview layers containing real color
  fill data. They MUST be independently toggleable and MUST NOT become part of
  the artwork pixels.

The adapter MUST reopen or otherwise structurally inspect the returned PSD and
render it on a navy/blue-jean preview before it can report PSD validation as
passed. A valid `8BPS` signature or matching layer names alone is insufficient.

## 10. Report

`report.json` MUST include job status, source dimensions, source hash, pipeline
version, selected strategy, alpha statistics, changed-pixel count, halo/frame
scores, protected-detail checks, warnings, review regions and artifact hashes.
It MUST also include mask provenance, the count of changed pixels inside every
protected region, PSD structure-validation evidence and the result of each
dark-garment preview check.

## 11. Quality and safety rules

- Hidden RGB under alpha zero is canonicalized safely.
- Premultiplied resize MUST NOT create a fringe.
- Internal light details MUST NOT be classified as external background.
- Protected regions MUST survive mask composition.
- Pixels in an approved protected region MUST have zero alpha loss and zero RGB
  modification relative to the frozen source/reference.
- A default perimeter-cleanup run MAY remove only pixels connected to the canvas
  border through approved removable pixels; enclosed holes and disconnected
  artwork details are preserved unless a reviewed explicit mask says otherwise.
- The source backup, working artwork and working mask in a PSD MUST contain
  real pixels. Empty placeholder layers fail PSD validation.
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
- A technically valid but visually fragmented candidate cannot become
  `passed`: the visual-quality gate must preserve the main subject, intentional
  foliage/details and a natural edge without isolated debris.
- Golden tests preserve protected details.
- Golden tests include an approved manual-perimeter reference and assert zero
  changed pixels in protected eyes, face, readable text, internal highlights and
  other declared protected details.
- The product has no mandatory Printify, MCP, Etsy or ChatGPT runtime dependency.
- Photopea can open the produced PSD, toggle real garment previews, inspect the
  working mask, and continue manual editing without reconstructing layers.

## 13. Semantic mask contract

The Skill or an approved vision provider MUST provide pixel-level artifacts
when semantic intent is present:

```text
semantic_protection_mask.png
candidate_removal_mask.png
uncertainty_mask.png
manual_corrections.png
```

The words `eyes`, `text`, `ears` or `leaves` are not pixel protection by
themselves. Missing semantic masks produce `review_required`.

## 14. Stage status contract

The report MUST distinguish `ai_mask_status`, `photopea_processing_status`,
`psd_validation_status`, `png_validation_status` and `overall_status`.
`overall_status=passed` is allowed only when all mandatory stages pass.

## 15. PSD conformance and visual proof

PSD export is a semantic output, not a container-format conversion. Before a
job becomes `passed`, the service MUST prove all of the following for the exact
returned artifact:

1. The file is a PSD returned by Photopea Live API.
2. The document contains the required pixel layers and the linked raster layer
   mask described in section 9.
3. `RESTORED` and `WITH GAPS` remain separate editable pixel layers, and their
   linked masks equal the corresponding candidate alpha masks.
4. The rendered artwork on black, navy and blue-jean backgrounds has no
   unapproved external halo.
5. Protected-detail diff checks report zero loss.

Failure to prove any item yields `review_required` or `failed`; the service MUST
not publish a formal PSD-only success.

## 16. Canvas policy

The policy MAY request a target canvas width, height, margin and DPI. Supported
production examples include 4200x4800 and 4500x5400. Artwork is resized with
premultiplied alpha, centered on a transparent canvas and never cropped.
