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
4. Poll until `passed`, `review_required`, `refused`, or `failed`. If the
   response contains `psd_export_status=pending`, download the core artifacts
   immediately; do not wait for Photopea unless the user explicitly requests
   PSD completion.
5. Return the downloaded artifact bundle and explain the report status. Use
   `--wait-for-psd` only when an explicit PSD wait is requested.

Example policy:

```json
{
  "primary_subject": "the main illustrated subject",
  "must_keep": ["all readable text", "face and thin details"],
  "keep_if_intentional": ["plants, smoke, splashes crossing the subject"],
  "remove_only": ["external flat background and confirmed edge debris"],
  "target_garments": ["black", "navy", "blue_jean", "white"],
  "edge_strategy": "auto_print_safe",
  "requested_variants": ["conservative", "artistic"],
  "mask_tuning": {
    "decision_id": "vision-review-<source-hash>-r1",
    "background_tolerance": 8,
    "fade_low_distance": 4,
    "fade_full_distance": 64,
    "fade_band_radius": 4,
    "confidence": 0.91
  },
  "visual_quality": {
    "reference_id": "manual-perimeter-panther-v1",
    "overall_score": 0.92,
    "subject_integrity": 0.98,
    "intentional_detail_score": 0.90,
    "edge_naturalness": 0.88,
    "artifact_free_score": 0.94,
    "confidence": 0.91,
    "reviewer_notes": ["Keep the panther, eyes, whiskers, and expressive foliage intact."]
  },
  "photopea_mask_plan": {
    "revision_id": "vision-mask-<source-hash>-r1",
    "subject_polygons": [[[0.10, 0.10], [0.90, 0.10], [0.90, 0.90], [0.10, 0.90]]],
    "remove_polygons": [],
    "protect_polygons": [],
    "feather_px": 2,
    "confidence": 0.92
  }
}
```

`mask_tuning` is not a project default. The vision/agent boundary MUST choose
it from the current source image and candidate previews, and record a new
`decision_id` for every mask revision. After the service emits candidate PNGs
and garment previews, the agent MUST inspect those intermediate artifacts and
either submit a revised policy/mask or accept the result. The service does not
call GPT implicitly and does not substitute fixed values when this decision is
absent; a missing or low-confidence decision remains `review_required`.

`visual_quality` is a required agent/vision judgement for a finished result.
It is not a decorative score: the service combines it with deterministic
fragmentation checks and refuses to pass a candidate with a torn edge,
isolated debris, lost intentional details, or low confidence. A text-only
description is never treated as visual understanding.

`photopea_mask_plan` is also an agent/vision output. It is a frozen, normalized
typed plan for the Photopea mask session, not JavaScript and not a pre-rendered
mask PNG. The agent must derive it from the current source and checkpoint
previews, increment `revision_id` after every correction, and omit it when the
geometry is ambiguous. A missing plan must not trigger a Python-generated PSD
fallback; the PSD stage must remain review-required or failed.

The intended Photopea loop is `source -> mask plan -> checkpoint -> vision
review -> typed correction -> checkpoint`. The current bridge rejects a
Photopea script/runtime error immediately and does not claim that this loop is
complete until a real same-document checkpoint/round-trip fixture passes.

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
  must receive one source document plus a typed mask plan; it must not receive
  seven pre-rendered PNG documents as the primary workflow.

## Repository implementation

The repository entrypoint is the asynchronous service documented in
`docs/deployment/local-service.md`. Domain processing is deterministic and
does not invoke a generative redraw model. Vision/model providers may be added
later only through declared ports and the OpenSpec change process.
