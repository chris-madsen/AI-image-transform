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
