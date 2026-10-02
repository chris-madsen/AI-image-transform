# Context Map

```text
Agent Job
   │ ProcessingPolicy / JobStatus
   ▼
Semantic Policy ───────► Mask Composition
   │                         │
   ▼                         ▼
Artwork Inspection ───► Print-safe Rendering
                              │
                              ▼
                       Review & Validation
                              │
                              ▼
                       Artifact Packaging
                              │
                              ├── PSD exporter
                              └── Photopea Live API adapter (mandatory for passed)
```

## Bounded contexts

1. Agent Job — lifecycle, idempotency and transport-facing status.
2. Artwork Inspection — immutable source facts and risk classification.
3. Semantic Policy — GPT-produced intent and protected details.
4. Mask Composition — revisions, connectivity and uncertainty.
5. Print-safe Rendering — alpha variants and previews.
6. Review & Validation — quality decision and review regions.
7. Artifact Packaging — immutable downloadable files and report.
8. Photopea Integration — mandatory browser/outer-environment exchange before `passed`.

Transport concerns such as Cloudflare Tunnel, bearer authentication and HTTP are adapters around these contexts, not domain contexts.
