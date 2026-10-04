# Ubiquitous Language

| Term | Canonical meaning |
|---|---|
| Artwork | Visible artistic composition that must be preserved. |
| Source | Immutable input bytes, canonical pixels and their hashes. |
| Intact reference | Source or approved reference that supplies authoritative protected artwork pixels. |
| Processing policy | Frozen, structured user intent; labels alone are never pixel masks. |
| Protected detail | Pixel region that must retain its source/reference RGB and alpha. |
| External background | Removable area connected to the canvas border through approved pixels. |
| Perimeter cleanup | Alpha-only removal of confirmed external background and fringe, starting at the canvas edge. |
| Removal mask | Pixel mask that identifies permitted external alpha removal. |
| Protection mask | Pixel mask that overrides removal and retains artwork pixels. |
| Final alpha mask | The composed alpha used by a candidate and the linked PSD layer mask. |
| Mask revision | Immutable alpha/mask version with parent identity, hashes and provenance. |
| Candidate | Named rendered artwork variant produced from one mask revision. |
| Garment preview | Non-destructive composite of a candidate over a named garment color. |
| Halo | Unwanted bright or colored fringe on a validation background. |
| PSD conformance | Proof that a Photopea PSD has required non-empty layers, a linked mask and valid rendering. |
| Artifact bundle | Immutable PNG, mask, preview, PSD and report set for one job. |
| Job | Aggregate governing one frozen source/policy pair and its lifecycle. |
| Review required | Terminal decision stating that evidence is missing or a safe automatic result is not proven. |
