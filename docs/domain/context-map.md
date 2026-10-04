# Context Map

```text
Skill / Agent Adapter
  │ frozen ProcessingPolicy + pixel masks
  ▼
Agent Job ─────────────► Artwork Inspection
  │                           │ inspection facts
  │                           ▼
  └──────────────► Mask Composition ◄──────── Semantic Policy
                       │ MaskRevision
                       ▼
                 Print-safe Rendering
                       │ candidates + previews
                       ▼
                Review & Validation
                       │ acceptance decision
                       ▼
                Artifact Packaging
                       │ PsdExporter port
                       ▼
        Photopea Live API anti-corruption layer
                       │ browser/Web Messaging
                       ▼
             External Photopea system
```

## Bounded contexts

1. **Agent Job** — lifecycle, idempotency, terminal decision and artifact discovery.
2. **Artwork Inspection** — immutable source facts, alpha profile and boundary risk.
3. **Semantic Policy** — frozen user intent and resolution of semantic intent to pixels.
4. **Mask Composition** — protection precedence, edge connectivity, uncertainty and revisions.
5. **Print-safe Rendering** — alpha-only variants, resize and garment previews.
6. **Review & Validation** — halo, frame, protected-pixel, PSD and decision evidence.
7. **Artifact Packaging** — immutable bundle, report and content hashes.

## External systems and anti-corruption layers

Photopea is not a domain bounded context. It is an external editing system. The
`PsdExporter` port and `PhotopeaLiveApiAdapter` form its anti-corruption layer:
the domain requests PSD conformance evidence and never receives browser,
iframe, `postMessage` or Photopea-specific objects.

Transport concerns such as Cloudflare Tunnel, bearer authentication and HTTP are
adapters around bounded contexts, not domain concepts.
