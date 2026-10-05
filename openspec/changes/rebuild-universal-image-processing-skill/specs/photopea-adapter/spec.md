# Photopea Live API Adapter

## ADDED Requirements

### Requirement: Photopea document construction
The adapter MUST transfer one source and one grayscale/alpha raster mask
carrier, then construct one document with separate editable artwork layers,
linked raster masks and real preview layers. Polygon plans and arbitrary
scripts MUST be rejected.

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

### Requirement: accepted revision is the single source of truth
The final transparent PNG, mask previews and PSD MUST be exported from the same
accepted Photopea revision. The adapter MUST bind source, checkpoint and mask
hashes and MUST reject stale revisions.

#### Scenario: stale correction
- **WHEN** a correction references another source or checkpoint
- **THEN** the adapter rejects it before opening Photopea

### Requirement: same-document checkpoint protocol
The Skill adapter MUST expose the Photopea session as bounded open, revision and
finalize operations. A revision MUST be submitted as one grayscale/alpha mask
carrier with its parent revision and checkpoint hashes; the bridge MUST keep
the same Photopea document alive until finalization or expiry.

#### Scenario: checkpoint correction
- **WHEN** vision rejects a checkpoint and returns a valid raster correction
- **THEN** the adapter submits the correction to the existing session and uses
  the returned checkpoint for the next review decision

### Requirement: no local PSD writer
The product MUST NOT create the production PSD using Python PSD libraries.

#### Scenario: PSD dependency
- **WHEN** PSD export is requested
- **THEN** the service calls the Photopea Live API adapter instead of a local writer
