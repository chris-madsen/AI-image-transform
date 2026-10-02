# Event Storming

## Domain Story

```text
SubmitProcessingJob
  → JobAccepted
  → SourceFrozen
  → ArtworkInspected
  → PolicyFrozen
  → MaskProposed
  → MaskRevisionCreated
  → CandidateRendered
  → PreviewGenerated
  → ValidationCompleted
  → ReviewRequired | ArtifactsPackaged | JobFailed
```

## Commands

- `SubmitProcessingJob`
- `InspectArtwork`
- `ResolvePolicy`
- `BuildMask`
- `RenderCandidate`
- `ValidateCandidate`
- `RequestReview`
- `PackageArtifacts`
- `GetArtifacts`

## Events

- `JobAccepted`
- `SourceFrozen`
- `ArtworkInspected`
- `PolicyFrozen`
- `MaskProposed`
- `MaskRevisionCreated`
- `CandidateRendered`
- `PreviewGenerated`
- `ValidationCompleted`
- `ReviewRequired`
- `ArtifactsPackaged`
- `JobFailed`

## Policies and invariants

- Source RGB is authoritative.
- No candidate with protected-detail loss or halo warning may be `passed`.
- Missing model/provider produces explicit review/failure, never silent fallback.
- Every artifact is linked to one job, source hash and pipeline version.

