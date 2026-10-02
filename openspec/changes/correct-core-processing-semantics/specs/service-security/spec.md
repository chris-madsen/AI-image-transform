# Service Security and Job Identity

## ADDED Requirements

### Requirement: path containment
Artifact names and job IDs MUST be validated and resolved paths MUST remain
under the job artifact directory.

#### Scenario: traversal artifact
- **WHEN** a download or variant name contains `..` or a path separator
- **THEN** the service rejects it without writing outside the job directory

### Requirement: policy-aware idempotency
The idempotency fingerprint MUST include source hash, canonical policy,
meaningful manifest fields and pipeline version. Conflicting reuse MUST return
HTTP 409.

#### Scenario: same key different policy
- **WHEN** the same key is reused with a different policy
- **THEN** the service returns conflict and does not return the old job

### Requirement: public authentication
A non-loopback/public deployment MUST refuse to start without bearer
authentication. Upload limits MUST be enforced while reading the request.

#### Scenario: missing public token
- **WHEN** a public bind is configured without a token
- **THEN** startup fails closed
