# Mask Composition

## ADDED Requirements

### Requirement: deterministic mask revision
A mask revision MUST combine edge-connected background, vision mask,
protected regions, local corrections, holes and uncertainty metadata.

#### Scenario: protected detail
- **WHEN** a candidate mask is composed
- **THEN** protected pixels cannot become transparent without a review signal

### Requirement: immutable revisions
Every revision MUST retain its parent identifier and provenance. Source RGB MUST
remain unchanged while alpha is transformed.

#### Scenario: revision provenance
- **WHEN** a user edits a mask
- **THEN** a new revision references its parent and preserves the frozen source
