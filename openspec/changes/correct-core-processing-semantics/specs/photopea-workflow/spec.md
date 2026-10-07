# Mandatory Photopea Workflow

## ADDED Requirements

### Requirement: editable PSD structure
The Photopea workflow MUST construct one document with non-empty `SOURCE
BACKUP`, separate `RESTORED` and `WITH GAPS` artwork layers, a grayscale
`WORKING MASK` carrier, linked raster masks for both artwork layers, and
independently toggleable real garment-fill layers.

#### Scenario: PSD round trip
- **WHEN** Photopea returns a PSD
- **THEN** the adapter verifies required layer pixels, linked mask equivalence and
  garment layer content in the exact returned artifact

### Requirement: PSD visual conformance
The workflow MUST prove that the returned PSD renders the artwork and final mask
correctly on black, navy and blue-jean backgrounds.

#### Scenario: dark preview
- **WHEN** a returned PSD has an unapproved halo, missing artwork or altered mask
- **THEN** PSD validation fails and overall status is not `passed`

### Requirement: incomplete PSD
Layer names, a valid `8BPS` signature, or empty placeholders MUST NOT satisfy
PSD validation.

#### Scenario: placeholder layer
- **WHEN** a required layer is empty, missing or unlinked
- **THEN** `psd_validation_status` is not passed and overall status is not passed

### Requirement: array-buffer transport
Large inputs MUST be sent through Live Messaging ArrayBuffer messages rather
than embedding all input images as base64 data in the iframe URL.

#### Scenario: large artwork
- **WHEN** artwork exceeds the configured URL-safe threshold
- **THEN** it is transferred after Photopea readiness through ArrayBuffer messages

### Requirement: bounded asynchronous PSD stage
The service MUST publish validated PNG, mask and preview artifacts before
starting the external Photopea export. PSD serialization MUST run as a bounded
background stage with an explicit pending, verified, unverified or failed
status; a slow browser MUST NOT block the core processing response.

#### Scenario: slow Photopea export
- **WHEN** Photopea does not return within five minutes
- **THEN** the job MUST expose the core artifacts and mark the PSD stage as
  failed or review-required without waiting indefinitely

### Requirement: Photopea-authored raster mask session
The bridge MUST open the source artwork once and create the working selection,
raster masks and editable layers inside that Photopea document. It MUST accept
the initial request with accepted/restored and conservative/gaps grayscale
mask carriers plus a validated `RasterMaskRevision`; revisions carry one
correction carrier.
It MUST reject polygon plans, arbitrary JavaScript and seven pre-rendered PNG
documents for the PSD path.

#### Scenario: initial mask revision
- **WHEN** the Skill submits one source, accepted/restored and conservative/gaps
  raster mask carriers, and a hash-bound initial revision
- **THEN** Photopea creates `RESTORED`, `WITH GAPS` and `WORKING MASK` from the
  source layer and returns artwork, mask and garment checkpoint previews

#### Scenario: iterative correction
- **WHEN** vision review identifies lost detail or external debris
- **THEN** the bridge applies a typed raster correction revision in the same live
  Photopea browser session, rebuilding the editable document from the original
  source plus one carrier without reopening seven image files

#### Scenario: session transport
- **WHEN** the Skill calls `POST /v1/photopea/sessions`, then submits a revision to
  `/v1/photopea/sessions/{id}/revisions`
- **THEN** the bridge keeps one browser session alive, returns a checkpoint after
  each revision, and accepts only one raster carrier with matching source,
  checkpoint and parent hashes; a revision may rebuild the editable document
  because literal same-document mutation is not reliable in the deployed
  Photopea scripting runtime

### Requirement: bounded vision review loop
The Skill MUST be able to request a checkpoint, pass it through a vision
provider, and submit a new mask revision. The loop MUST enforce a maximum
revision count and wall-clock budget, and MUST fail closed when the provider
does not return a valid correction or acceptance assessment.

#### Scenario: invalid checkpoint decision
- **WHEN** the vision provider returns no decision, a stale raster revision or
  a decision after the revision/time budget is exhausted
- **THEN** the session stops with `review_required` or `failed` and MUST NOT
  export a PSD as `passed`
