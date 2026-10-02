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

1. Convert the user's natural-language request into `ProcessingPolicy` JSON.
2. Keep `must_keep`, `keep_if_intentional`, and `remove_only` explicit.
3. Send the source image and policy to `ARTWORK_SERVICE_URL` using
   `scripts/submit_artwork_job.py`.
4. Poll until `passed`, `review_required`, `refused`, or `failed`.
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
  "requested_variants": ["conservative", "artistic"]
}
```

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
- Treat automatic SAM2 mask selection as a heuristic; require preview review
  before using it as a protection mask.
- If the result damages thin details or leaves a visible halo, stop and report
  the candidate as failed instead of presenting it as final.
- If the service is unavailable, do not silently run a different model or
  claim that the image was processed.
- PSD export is performed by the Photopea Live bridge, not by a Python PSD
  writer. The bridge is not controlled by mouse-coordinate automation.

## Repository implementation

The repository entrypoint is the asynchronous service documented in
`docs/deployment/local-service.md`. Domain processing is deterministic and
does not invoke a generative redraw model. Vision/model providers may be added
later only through declared ports and the OpenSpec change process.
