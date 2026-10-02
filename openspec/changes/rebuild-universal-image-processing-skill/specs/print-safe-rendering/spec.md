# Print-safe Rendering

## ADDED Requirements

### Requirement: alpha-only rendering
The renderer MUST preserve source RGB except for explicit hidden-RGB cleanup.
Resize MUST use premultiplied alpha.

#### Scenario: source preservation
- **WHEN** a candidate is rendered
- **THEN** visible source RGB is unchanged and resize uses premultiplied alpha

### Requirement: variants and previews
The service MUST support conservative, artistic, binary-alpha, controlled-soft-
alpha and halftone outputs, plus black, white, gray, navy, blue-jean and DTG
underbase previews.

#### Scenario: halftone
- **WHEN** a halftone variant is requested
- **THEN** its alpha channel contains only `0` and `255`

#### Scenario: glow or fringe
- **WHEN** continuous alpha creates a visible print halo
- **THEN** validation cannot return `passed`
