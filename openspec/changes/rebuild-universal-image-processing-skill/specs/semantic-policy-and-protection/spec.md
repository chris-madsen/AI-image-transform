# Semantic Policy and Protection

## ADDED Requirements

### Requirement: frozen policy
The service MUST accept only validated, immutable `ProcessingPolicy` values.
The policy includes subject, must-keep regions, conditional details,
remove-only intent, target garments, edge strategy and requested variants.

#### Scenario: invalid policy
- **WHEN** policy fields are missing, malformed or ambiguous
- **THEN** the job becomes `review_required` and no unsafe fallback is selected

### Requirement: protected intent
Protected details MUST be carried into mask composition and validation.

#### Scenario: protected region
- **WHEN** a policy marks text as must-keep
- **THEN** mask composition and validation check that the text remains visible
