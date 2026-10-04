# Artifact Export

## ADDED Requirements

### Requirement: immutable bundle
The service MUST emit PNG variants, masks, garment previews, a DTG preview and
`report.json` with hashes and validation evidence.

#### Scenario: bundle manifest
- **WHEN** a job reaches artifact packaging
- **THEN** every emitted file has a hash and appears in the report

### Requirement: editable Photopea PSD
The editable PSD MUST be created through Photopea Live API as one document with
non-empty `SOURCE BACKUP`, separate `RESTORED` and `WITH GAPS` artwork layers,
and a grayscale `WORKING MASK`, with linked raster masks on both candidates,
and independently toggleable garment-fill layers.

#### Scenario: PSD content
- **WHEN** the adapter returns a PSD
- **THEN** structure validation proves the required layers contain the source,
  candidate RGB, final grayscale mask and real preview fill data

### Requirement: PSD conformance evidence
A PSD signature or matching layer names alone MUST NOT satisfy export
validation. The artifact report MUST include exact PSD structure and rendering
evidence.

#### Scenario: placeholder layers
- **WHEN** any required PSD layer is empty, missing, unlinked or unverified
- **THEN** PSD validation fails and the job cannot become `passed`
