---
name: universal-image-matting
description: Process print artwork through the local cleaner service, preserving source RGB and producing transparent PNGs, validation previews and a Photopea PSD.
metadata:
  short-description: Local alpha matting with halo checks
---

# Universal image matting

Use this skill for removing unwanted backgrounds, halos, glow, or weak alpha
from arbitrary images where the visible RGB artwork must not be regenerated.

## Service-first workflow

When the local image-processing service is available, this skill is an agent
adapter, not a second image-processing engine:

1. Convert the user's natural-language request into intent-only
   `ProcessingPolicy` JSON. Do not invent or upload a finished mask.
2. Keep `must_keep`, `keep_if_intentional`, and `remove_only` explicit.
3. Send the source image and policy to `ARTWORK_SERVICE_URL` using
   `scripts/submit_artwork_job.py`.
4. Poll until `passed`, `review_required`, `refused`, or `failed`. The helper
   waits for the Photopea PSD stage by default; this Skill is a complete PNG +
   editable-PSD workflow and must not finish while `psd_export_status=pending`.
   Use the explicit `--core-only` opt-out only for diagnostics, and report that
   the result is not a complete print artifact.
5. Return the downloaded artifact bundle and explain the report status.

Example policy:

```json
{
  "primary_subject": "the main illustrated subject",
  "must_keep": ["all readable text", "face and thin details"],
  "keep_if_intentional": ["plants, smoke, splashes crossing the subject"],
  "remove_only": ["external flat background and confirmed edge debris"],
  "target_garments": ["black", "navy", "blue_jean", "white"],
  "edge_strategy": "auto_print_safe",
  "requested_variants": ["controlled_soft_alpha", "halftone"]
}
```

`mask_tuning`, `visual_quality` and raster revision hashes are runtime evidence,
not claims supplied in the initial policy. After Photopea emits a checkpoint,
the production vision adapter MUST inspect the exact transparent artwork, mask
and garment-preview bytes/URLs and either accept or submit a typed internal
correction. A hash-only object is not inspectable visual evidence.

`visual_quality` is a required agent/vision judgement for a finished result.
It is not a decorative score: the service combines it with deterministic
fragmentation checks and refuses to pass a candidate with a torn edge,
isolated debris, lost intentional details, or low confidence. A text-only
description is never treated as visual understanding.

The job caller MUST NOT provide `photopea_mask` or `photopea_mask_revision`.
Automatic proposal pixels come from a configured specialized model provider;
Photopea authors the editable working mask. Only after a checkpoint exists may
the vision adapter return an internal raster correction bound to
`source_sha256`, `checkpoint_sha256`, `base_mask_sha256` and
`result_mask_sha256`. Stale or cross-artwork revisions are rejected.

The intended Photopea loop is `source + internal model proposals ->
Photopea-authored mask -> reviewable checkpoint -> vision review -> internal
raster correction -> checkpoint`, in one bounded Photopea document.
The bridge rejects arbitrary scripts and polygon plans immediately and does not
claim that this loop is complete until a real same-document
checkpoint/round-trip fixture passes.

The service returns PNG, masks, dark-garment previews, a JSON report and an
editable PSD. `review_required`, `refused`, and `failed` are not successes and
must never be silently presented as a finished print.

Run the helper locally:

```bash
ARTWORK_SERVICE_URL=http://127.0.0.1:8000 \
  python skill/universal-image-matting/scripts/submit_artwork_job.py \
  --source input.png --policy policy.json --out artifacts/job
```

For a Named Cloudflare Tunnel, set the HTTPS service URL and inject the bearer
token through `ARTWORK_SERVICE_TOKEN`; never put the token in this file or in
the policy JSON.

## Operating rules

- Treat the input RGB as authoritative. The normal output changes alpha only.
- Never use lossy WebP for an intermediate alpha-bearing image.
- Use lossless WebP only as a verified storage/input variant. Verify alpha and
  visible RGB separately: hidden RGB under fully transparent pixels may be
  canonicalized by the codec.
- Resize RGBA through premultiplied alpha; do not resize straight RGBA when
  creating a model input.
- Preserve the original dimensions and never crop.
- Always produce alpha, navy, black, white, and checkerboard previews.
- If a model cannot be loaded, report the exact missing dependency or model
  rather than silently falling back to a different model.
- Use a declared specialized segmentation/matting implementation for proposal
  pixels. The target stack is BiRefNet HR-matting, BEN2, SAM 2.1 protection and
  optional ViTMatte refinement. Pin the model version, license and weights hash.
- Never ask an LLM to paint the production alpha mask. LLM vision may interpret
  intent and accept/reject rendered checkpoints.
- Do not invent `visual_quality` scores. If the agent cannot inspect the
  artwork and candidate previews, omit the assessment and let the service
  return `review_required`.
- Evaluate the candidate on the source artwork and on black, navy, blue-jean
  and white previews. Prefer a few large expressive leaves/details over many
  isolated semi-transparent pixels.
- Compare every candidate against the source and the previous revision before
  accepting it. In particular check ears, whiskers, foliage above the head,
  internal light details, and the transition from opaque artwork to alpha 0.
- Treat automatic SAM2 mask selection as a heuristic; require preview review
  before using it as a protection mask.
- If the result damages thin details or leaves a visible halo, stop and report
  the candidate as failed instead of presenting it as final.
- If the service is unavailable, do not silently run a different model or
  claim that the image was processed.
- PSD export is performed by the Photopea Live bridge, not by a Python PSD
  writer. The bridge is not controlled by mouse-coordinate automation. The
  bridge has a bounded hard timeout; a slow export or script error is an
  explicit failed PSD stage, never an indefinitely running job. The bridge
  must receive one source document plus internal proposal/protection pixels and
  reviewed corrections; it must not receive a caller-supplied final mask, seven
  pre-rendered PNG documents or a polygon plan as the primary workflow.

## Repository implementation

The repository entrypoint is the asynchronous service documented in
`docs/deployment/local-service.md`. Domain processing is deterministic and
does not invoke a generative redraw model. The repository is not complete until
at least one concrete specialized model provider and the production checkpoint
review loop are implemented through declared ports and the OpenSpec change
process.
