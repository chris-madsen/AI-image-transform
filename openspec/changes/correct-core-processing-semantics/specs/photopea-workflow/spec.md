# Mandatory Photopea Workflow

## ADDED Requirements

### Requirement: editable PSD structure
The Photopea Live API workflow MUST create one document with named source,
working artwork, working mask, raster mask and garment test layers. The service
MUST validate the returned PSD structure before reporting success.

#### Scenario: PSD round trip
- **WHEN** Photopea returns a PSD
- **THEN** the adapter reopens or inspects it and verifies required layers and masks

#### Scenario: incomplete PSD
- **WHEN** required structure cannot be verified
- **THEN** `psd_validation_status` is not passed and overall status is not passed

### Requirement: array-buffer transport
Large inputs MUST be sent through Live Messaging ArrayBuffer messages rather than
embedding all input images as base64 data in the iframe URL.

#### Scenario: large artwork
- **WHEN** artwork exceeds the configured URL-safe threshold
- **THEN** it is transferred after Photopea readiness through ArrayBuffer messages
