# Artifact Export

## ADDED Requirements

### Requirement: immutable bundle
The service MUST emit PNG variants, masks, garment previews, DTG preview and
`report.json` with hashes and validation data.

#### Scenario: bundle manifest
- **WHEN** a job reaches artifact packaging
- **THEN** every emitted file has a hash and appears in the report

### Requirement: Photopea PSD
The editable PSD MUST be created through the Photopea Live API adapter and MUST
contain `SOURCE BACKUP`, `WORKING ART`, `WORKING MASK` and print test layers.

#### Scenario: Photopea unavailable
- **WHEN** the Photopea Live API adapter is unavailable
- **THEN** the job MUST NOT become `passed`; it becomes `review_required` or `failed`
