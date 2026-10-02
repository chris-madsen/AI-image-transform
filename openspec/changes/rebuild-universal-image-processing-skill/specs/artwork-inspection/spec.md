# Artwork Inspection

## ADDED Requirements

### Requirement: source inspection
The service MUST freeze the source hash, dimensions, color mode, alpha profile,
hidden RGB statistics and edge-touching classification before mutation.

#### Scenario: RGBA source
- **WHEN** a source contains alpha
- **THEN** the report records dimensions, alpha statistics and source hash

### Requirement: edge-connected background
The service MUST distinguish edge-connected background from internal regions.

#### Scenario: internal same-color detail
- **WHEN** a light region is enclosed by protected artwork
- **THEN** it MUST NOT be classified as removable external background
