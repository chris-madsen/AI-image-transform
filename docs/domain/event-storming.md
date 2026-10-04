# Event Storming

## Aggregate boundaries

- **ProcessingJob** is the aggregate root for source identity, frozen policy,
  terminal status and artifact bundle identity.
- **MaskRevision** is an immutable value owned or referenced by a job; a new
  revision never mutates its parent.
- **ArtifactBundle** is immutable after `ArtifactsPackaged`.

## Domain story

```text
SubmitProcessingJob
  → JobAccepted
  → SourceFrozen
  → ArtworkInspected
  → PolicyFrozen
  → PixelMasksResolved | SemanticResolutionMissing
  → PerimeterRemovalProposed
  → MaskRevisionCreated | MaskCompositionRefused
  → CandidateRendered
  → GarmentPreviewGenerated
  → CandidateValidated
  → PsdExportRequested
  → PsdExported | PsdExportFailed
  → PsdStructureValidated | PsdConformanceFailed
  → ArtifactsPackaged
  → JobPassed | ReviewRequired | JobRefused | JobFailed
```

## Commands

- `SubmitProcessingJob`
- `FreezeSource`
- `FreezePolicy`
- `InspectArtwork`
- `ResolvePixelMasks`
- `ProposePerimeterRemoval`
- `CreateMaskRevision`
- `RenderCandidate`
- `GenerateGarmentPreview`
- `ValidateCandidate`
- `RequestPsdExport`
- `ValidatePsdConformance`
- `PackageArtifacts`
- `RequestReview`
- `RefuseJob`

## Policies

- A semantic label without a pixel mask emits `SemanticResolutionMissing` and
  cannot produce `JobPassed`.
- Protection pixels take precedence over removal pixels.
- Only approved edge-connected pixels are removable in default perimeter mode.
- A candidate can pass only if protected-pixel loss is zero and its required
  validation previews pass.
- A job can pass only if PNG validation and PSD conformance both pass.

## Read models

- **Job status**: lifecycle status, warnings, review regions and stage results.
- **Inspection report**: geometry, alpha profile, edge classification and risk.
- **Mask evidence**: provenance, hashes, coverage and protected-pixel diff.
- **Validation report**: per-variant halo/frame/protection results.
- **Artifact manifest**: immutable paths, hashes and PSD conformance evidence.
