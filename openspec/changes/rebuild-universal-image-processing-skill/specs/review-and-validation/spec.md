# Review and Validation

## ADDED Requirements

### Requirement: print validation
Validation MUST check halo score, frame score, protected-detail preservation,
new transparent holes, bounds, aspect ratio, resolution and DTG underbase.

#### Scenario: safe result
- **WHEN** all checks pass and PSD export succeeds
- **THEN** the job may become `passed`

#### Scenario: ambiguous result
- **WHEN** a required check is uncertain or unavailable
- **THEN** the job becomes `review_required` or `refused`
