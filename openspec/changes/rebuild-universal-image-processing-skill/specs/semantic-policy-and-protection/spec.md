# Semantic Policy and Protection

## ADDED Requirements

### Requirement: frozen policy
The service MUST accept only validated immutable `ProcessingPolicy` values with
subject, must-keep intent, remove-only intent, garments, edge strategy and
requested variants.

#### Scenario: invalid policy
- **WHEN** policy fields are malformed or ambiguous
- **THEN** ingestion returns a structured error or the job becomes `review_required`

### Requirement: pixel-level semantic protection
Words such as `eyes`, `text` or `leaves` MUST NOT be treated as pixel masks.
Semantic intent requires a resolved protection mask with provenance.

#### Scenario: unresolved semantic intent
- **WHEN** a policy requires protected semantic details but no pixel mask exists
- **THEN** the job is `review_required` and cannot become `passed`

### Requirement: protected-pixel preservation
Protected pixels MUST retain their source/reference alpha and visible RGB across
mask composition and rendering.

#### Scenario: protected region
- **WHEN** a valid protection mask is supplied
- **THEN** protected-pixel alpha loss and RGB diff are both zero
