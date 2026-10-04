# Mask Composition

## ADDED Requirements

### Requirement: deterministic mask revision
A mask revision MUST combine approved edge-connected removal pixels, resolved
pixel-level protection, local corrections, holes and uncertainty metadata.

#### Scenario: protected detail
- **WHEN** a candidate mask is composed
- **THEN** protection pixels override removal and cannot become transparent

### Requirement: manual-equivalent perimeter cleanup
The default cleanup MUST begin at the canvas border and remove only approved
edge-connected pixels. It MUST NOT remove enclosed regions or disconnected
artwork by a whole-image color rule.

#### Scenario: internal same-color region
- **WHEN** an internal highlight has colors similar to removable background
- **THEN** it remains unchanged unless an explicit reviewed removal mask includes it

### Requirement: intact reference precedence
When an intact reference or semantic protection mask is supplied, its protected
pixels MUST take precedence over a perimeter-clean removal proposal.

#### Scenario: protected eyes and foliage
- **WHEN** a removal proposal overlaps approved protected eyes or foliage
- **THEN** final alpha and RGB for those protected pixels equal the source/reference

### Requirement: immutable revisions
Every revision MUST retain parent identity and provenance. Source RGB MUST
remain unchanged while alpha is transformed.

#### Scenario: revision provenance
- **WHEN** a user edits a mask
- **THEN** a new revision references its parent and preserves the frozen source
