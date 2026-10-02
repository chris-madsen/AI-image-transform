# Semantic Mask Boundary

## ADDED Requirements

### Requirement: resolved mask bundle
The service MUST accept a `ResolvedMaskBundle` containing semantic protection,
removable background, uncertainty and manual correction masks, each with shape,
hash, confidence and provenance.

#### Scenario: unresolved text intent
- **WHEN** a policy contains semantic requests without corresponding pixel masks
- **THEN** the job MUST be `review_required` and MUST NOT be `passed`

#### Scenario: supplied protection mask
- **WHEN** a valid protection mask is supplied
- **THEN** mask composition MUST preserve its nonzero pixels

### Requirement: explicit stage status
The report MUST expose `ai_mask_status`, `photopea_processing_status`,
`psd_validation_status`, `png_validation_status` and `overall_status`.

#### Scenario: complete success
- **WHEN** all required stages pass
- **THEN** and only then may `overall_status` be `passed`
