# Print Validation

## ADDED Requirements

### Requirement: DTG underbase approximation
The DTG preview MUST model a garment color, white underbase threshold/spread and
color artwork composite. It MUST NOT be byte-identical to the ordinary white
preview and MUST be labeled as an approximation.

#### Scenario: dark garment preview
- **WHEN** a navy or black garment is requested
- **THEN** the report identifies the garment and underbase approximation

### Requirement: per-variant validation
Every emitted artwork variant MUST have its own validation result. A dangerous
variant MUST prevent the overall job from being `passed`.

#### Scenario: unsafe artistic variant
- **WHEN** conservative passes but artistic fails protected-detail validation
- **THEN** the job is not `passed` and the failing variant is listed

### Requirement: protected-pixel and PSD proof
A job MUST prove zero protected-pixel loss and PSD conformance in addition to
PNG preview scores before it can report `passed`.

#### Scenario: PNG-only success
- **WHEN** PNG previews pass but protected-pixel or PSD proof is missing
- **THEN** the job is `review_required` or `failed`, never `passed`

### Requirement: beauty-aware acceptance
PNG and PSD validation MUST include the frozen visual-quality assessment and
must not reduce acceptance to alpha/container validity. The report MUST expose
the quality score, deterministic edge-fragmentation score and assessment
confidence.

#### Scenario: technically valid but ugly mask
- **WHEN** a candidate has a valid PNG/PSD but loses intentional foliage,
  creates isolated debris, or has a torn silhouette
- **THEN** validation MUST be `review_required` and MUST identify
  `visual_quality` or `edge_aesthetics` as a review region
