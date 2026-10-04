# Review and Validation

## ADDED Requirements

### Requirement: print validation
Validation MUST check halo score, frame score, protected-pixel preservation, new
transparent holes, bounds, aspect ratio, resolution and DTG-underbase behavior.

#### Scenario: safe result
- **WHEN** all PNG checks and PSD conformance checks pass
- **THEN** the job may become `passed`

#### Scenario: ambiguous result
- **WHEN** a required check is uncertain or unavailable
- **THEN** the job becomes `review_required` or `refused`

### Requirement: zero protected-pixel loss
A candidate with alpha loss or visible RGB changes in an approved protected
region MUST NOT pass validation.

#### Scenario: protection regression
- **WHEN** a rendered candidate changes one protected eye, glyph or leaf pixel
- **THEN** validation reports the region and prevents `passed`

### Requirement: per-artifact acceptance evidence
The report MUST retain per-variant validation and the exact evidence for final
PSD conformance.

#### Scenario: invalid PSD after valid PNG
- **WHEN** PNG validation passes but PSD validation fails
- **THEN** the job is not `passed` and reports the PSD failure separately
