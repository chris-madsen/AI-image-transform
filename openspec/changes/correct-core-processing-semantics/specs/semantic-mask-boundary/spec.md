# Semantic Mask Boundary

## ADDED Requirements

### Requirement: resolved mask bundle
The service MUST accept a resolved mask bundle containing semantic protection,
removable background, uncertainty and manual correction masks, each with shape,
hash, confidence and provenance.

#### Scenario: unresolved text intent
- **WHEN** a policy contains semantic requests without corresponding pixel masks
- **THEN** the job MUST be `review_required` and MUST NOT be `passed`

### Requirement: protection precedence
Protection masks or intact references MUST override candidate removal pixels and
retain source/reference RGB and alpha in protected regions.

#### Scenario: supplied protection mask
- **WHEN** a valid protection mask overlaps a removal proposal
- **THEN** every protected pixel has zero alpha loss and zero visible RGB diff

### Requirement: manual-equivalent perimeter scope
Default removal MUST be restricted to approved edge-connected pixels from the
canvas border and MUST preserve enclosed or disconnected artwork.

#### Scenario: internal light detail
- **WHEN** an internal light region resembles the external background
- **THEN** it remains artwork unless an explicit reviewed mask permits removal

### Requirement: explicit stage status
The report MUST expose `ai_mask_status`, `photopea_processing_status`,
`psd_validation_status`, `png_validation_status` and `overall_status`.

#### Scenario: complete success
- **WHEN** all required stages pass
- **THEN** and only then may `overall_status` be `passed`

### Requirement: visual quality assessment
The agent or vision provider MUST provide a frozen visual-quality assessment
when semantic artwork intent is processed. The assessment MUST score subject
integrity, intentional-detail preservation, edge naturalness, artifact freedom
and confidence against a named reference or review rubric.

#### Scenario: missing or weak visual judgement
- **WHEN** the assessment is missing, low-confidence or below the configured
  quality threshold
- **THEN** the job MUST be `review_required` and MUST NOT be reported as a
  finished print

#### Scenario: fragmented candidate
- **WHEN** deterministic checks find isolated alpha debris or a fragmented
  edge despite a high claimed score
- **THEN** the quality gate MUST override the claim and require review

### Requirement: per-artwork mask tuning
The agent/vision boundary MUST freeze background and perimeter-fade parameters
for each artwork revision. The processing service MUST use those frozen values
for that revision and MUST NOT treat repository defaults as an AI decision.

#### Scenario: missing tuning decision
- **WHEN** a job has no per-artwork mask tuning or its confidence is below the
  configured threshold
- **THEN** the job MUST remain `review_required` and MUST expose the missing or
  weak decision in the report

#### Scenario: intermediate candidate review
- **WHEN** conservative/artistic candidates and garment previews are emitted
- **THEN** the agent MUST inspect them and either submit a new mask revision or
  freeze an explicit acceptance assessment before completion

### Requirement: typed vision correction
Vision review MUST return a frozen correction plan composed of normalized
polygon regions and bounded selection operations. Arbitrary Photopea JavaScript
MUST NOT cross the Skill boundary.

#### Scenario: protect a missed detail
- **WHEN** vision review detects a lost ear, eye, glyph or intentional foliage
- **THEN** the correction plan adds a protected polygon and the next Photopea
  checkpoint preserves that region

#### Scenario: remove an edge defect
- **WHEN** vision review detects isolated external debris
- **THEN** the correction plan subtracts a bounded polygon from the external
  perimeter selection and the next checkpoint is revalidated
