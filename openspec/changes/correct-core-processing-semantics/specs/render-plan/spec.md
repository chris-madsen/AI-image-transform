# Render Plan

## ADDED Requirements

### Requirement: mode-aware rendering
The service MUST create a `RenderPlan` from processing mode, edge strategy,
target garments, inspection and uncertainty. Every requested variant MUST map
to a fixed safe renderer.

#### Scenario: halftone mode
- **WHEN** `HALFTONE_DARK_GARMENT` or `HALFTONE` is selected
- **THEN** the chosen output MUST use the configured cell size and binary alpha

#### Scenario: inspect mode
- **WHEN** mode is `INSPECT`
- **THEN** the service MUST emit diagnostics without claiming a processed `passed` artwork

### Requirement: strict variant names
Requested variants MUST be an enum or fixed allow-list and MUST NOT be used as
raw filesystem path components.

#### Scenario: unknown variant
- **WHEN** an unknown or traversal-like variant is submitted
- **THEN** policy ingestion returns a structured validation error
