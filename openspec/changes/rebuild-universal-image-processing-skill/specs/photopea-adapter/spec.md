# Photopea Live API Adapter

## ADDED Requirements

### Requirement: Photopea export
`PhotopeaLiveApiAdapter` MUST send source artwork and mask data to a Photopea
Live API outer environment and accept only a returned PSD payload.

#### Scenario: valid PSD
- **WHEN** Photopea returns bytes beginning with `8BPS`
- **THEN** the adapter stores them as the editable PSD artifact

#### Scenario: invalid response
- **WHEN** the response is unavailable or is not a PSD
- **THEN** the adapter returns an explicit error and the job is not `passed`

### Requirement: no local PSD writer
The product MUST NOT create the production PSD using Python PSD libraries.

#### Scenario: PSD dependency
- **WHEN** PSD export is requested
- **THEN** the service calls the Photopea Live API adapter instead of a local writer
