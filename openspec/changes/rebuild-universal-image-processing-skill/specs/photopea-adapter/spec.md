# Photopea Live API Adapter

## ADDED Requirements

### Requirement: Photopea document construction
The adapter MUST transfer source, the artistic `RESTORED` candidate, the
conservative `WITH GAPS` candidate, both final masks and construct one document
with separate editable artwork layers and real preview layers.

#### Scenario: valid editable PSD
- **WHEN** Photopea returns a PSD
- **THEN** the adapter verifies non-empty `RESTORED` and `WITH GAPS` pixel
  layers and linked masks whose pixels equal their candidate alpha masks

### Requirement: visual conformance
The adapter MUST validate the returned PSD by reopening or inspecting it and by
rendering its artwork over black, navy and blue-jean preview backgrounds.

#### Scenario: dark-garment proof
- **WHEN** the dark-garment preview contains an unapproved halo or lacks artwork
- **THEN** PSD conformance fails and the job is not `passed`

### Requirement: no local PSD writer
The product MUST NOT create the production PSD using Python PSD libraries.

#### Scenario: PSD dependency
- **WHEN** PSD export is requested
- **THEN** the service calls the Photopea Live API adapter instead of a local writer
