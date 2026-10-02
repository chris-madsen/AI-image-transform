# Agent Job Contract

## ADDED Requirements

### Requirement: asynchronous job lifecycle
The service MUST accept a job and return a job identifier without waiting for
processing. Valid states are `accepted`, `running`, `review_required`, `passed`,
`refused` and `failed`.

#### Scenario: submit job
- **WHEN** a valid multipart source, manifest and frozen policy are submitted
- **THEN** the service returns `202`, `job_id`, status `accepted` and `poll_url`

#### Scenario: idempotent retry
- **WHEN** the same idempotency key and source hash are submitted again
- **THEN** the existing job is returned and no duplicate job is created

### Requirement: artifact discovery
The service MUST expose status, artifact listing and artifact download endpoints.

#### Scenario: terminal job
- **WHEN** processing reaches a terminal state
- **THEN** status includes report, warnings and artifact metadata
