# Local service and Named Cloudflare Tunnel

## Local run

```bash
uv sync --extra dev
ARTWORK_SERVICE_TOKEN='change-me' make service
```

The service stores temporary jobs under `artifacts/service/`. Set
`ARTIFACT_ROOT`, `HOST`, `PORT`, `MAX_SOURCE_BYTES`, and
`ARTWORK_SERVICE_TOKEN` through the environment. Secrets must not be written
to the repository or logs.

## Named tunnel

Expose only the local service through a Named Cloudflare Tunnel and use its
stable HTTPS hostname as `ARTWORK_SERVICE_URL` in the Skill runtime. Keep the
bearer secret in the runtime environment or secret manager. Cloudflare is only
transport; the processing service must remain usable at localhost when the
tunnel is unavailable.

## Operational checks

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/metrics
```

Printify credentials are intentionally not accepted by this service.

## Photopea Live API adapter

Run the outer-environment bridge separately:

```bash
cd bridge
npm install
npx playwright install chromium
PHOTOPEA_LIVE_API_TOKEN='change-me' npm start
```

Then configure the image service:

```bash
PHOTOPEA_LIVE_API_URL=http://127.0.0.1:8787 \
PHOTOPEA_LIVE_API_TOKEN='change-me' \
PHOTOPEA_REVIEW_SECRET='shared-runtime-secret' \
PHOTOPEA_LIVE_API_TIMEOUT=300 \
make service
```

For the Photopea outer environment, use the matching millisecond timeout for
large PSD serialization:

```bash
PHOTOPEA_EXPORT_TIMEOUT_MS=300000 npm start
```

The single-source typed Photopea mask session has a separate fail-fast limit:

```bash
PHOTOPEA_SESSION_TIMEOUT_MS=300000 npm start
```

The service also enforces a total review budget. Keep it at or below the
Photopea session timeout unless the measured deployment SLA is intentionally
changed:

```bash
PHOTOPEA_REVIEW_BUDGET_SECONDS=300
```

Configure the external multimodal checkpoint reviewer separately:

```bash
VISION_REVIEW_ENDPOINT='https://vision.example/review' \
VISION_REVIEW_TOKEN='change-me' \
VISION_REVIEW_TIMEOUT=120 \
make service
```

An OpenAI-compatible deployment adapter is provided for the multimodal visual
gate. It is intentionally fail-closed: it can accept a checkpoint only with a
high-confidence structured response; it does not generate a correction mask.
Run it separately and point `VISION_REVIEW_ENDPOINT` at it:

```bash
VISION_LLM_API_KEY='injected-at-runtime' \
VISION_LLM_MODEL='<vision-model-release>' \
VISION_LLM_ENDPOINT='https://api.openai.com/v1/chat/completions' \
uvicorn scripts.serve_vision_reviewer:app --host 127.0.0.1 --port 8010
```

If the model rejects a checkpoint, the processing service remains
`review_required`; a trusted raster-correction provider is still required for
an automatic revision. Never treat a text-only model response as visual
evidence and never put the API key in repository files.

Configure both independent proposal endpoints and their release pins before
enabling automatic model proposals:

```bash
BIREFNET_ENDPOINT='https://matting.internal/birefnet' \
BIREFNET_MODEL_VERSION='<pinned-release>' \
BIREFNET_MODEL_LICENSE='<recorded-license>' \
BIREFNET_WEIGHTS_SHA256='<64-lowercase-hex-characters>' \
BEN2_ENDPOINT='https://matting.internal/ben2' \
BEN2_MODEL_VERSION='<pinned-release>' \
BEN2_MODEL_LICENSE='<recorded-license>' \
BEN2_WEIGHTS_SHA256='<64-lowercase-hex-characters>' \
SAM2_ENDPOINT='https://matting.internal/sam2-protection' \
SAM2_MODEL_VERSION='<pinned-release>' \
SAM2_MODEL_LICENSE='<recorded-license>' \
SAM2_WEIGHTS_SHA256='<64-lowercase-hex-characters>' \
make service
```

For the Windows Vega 56 host, use the local DirectML ONNX proposal server
instead of a hosted or paid inference API. Its LAN address can be used for
`BIREFNET_ENDPOINT`/`BEN2_ENDPOINT` only after the model has passed the Windows
benchmark and the endpoint health metadata has been recorded. Keep the Windows
port on the home LAN/firewall; do not expose it through the public Cloudflare
tunnel.

The service rejects missing or mismatched model metadata and does not fall
back to a color heuristic. SAM 2.1 protection is served by the deployment-only
`scripts/serve_sam2_protection.py`; it returns only source-bound protection and
uncertainty carriers and excludes border-touching masks. Optional ViTMatte
refinement still requires its own deployment adapter and release manifest; see
`docs/deployment/model-stack.md`.

The reviewer receives source, checkpoint artwork, grayscale mask, red contour
overlay and dark-garment previews. It
must return a typed acceptance or one hash-bound grayscale correction carrier;
it cannot return Photopea scripts. The bridge requires the same
`PHOTOPEA_REVIEW_SECRET` and accepts finalization only with a one-shot HMAC
token bound to source, revision and current checkpoint hashes. If the reviewer
or secret is absent/invalid, the service fails closed with
`review_required`/failed instead of passing PSD.

Core PNG, mask and preview artifacts are produced before the Photopea adapter
is scheduled. PSD export runs in a separate background executor and updates the
same job when it completes; clients can download the core artifacts while PSD
is pending. The adapter has a hard five-minute timeout. Without a completed
Photopea export the service MUST return `review_required` rather than claiming
a completed PSD job.

Artifact provenance is explicit in both the job report and the artifact-list
endpoint. Core renders have `role: proposal` and
`authoritative: false`; they are diagnostics only. The accepted Photopea
checkpoint exports and the PSD have `role: authoritative` and
`authoritative: true`. The report's `artifact_set.authoritative_artifacts`
contains the only files that a client may deliver as the accepted result. A
missing or unverified authoritative set remains `review_required`.

The Photopea session uses a raster mask carrier and canonical charID mask
creation; polygon selection plans are rejected. The initial checkpoint is
authored in one Photopea document. Revisions stay in one live browser session
and rebuild the editable document from the original source plus one typed
correction carrier because the deployed scripting runtime cannot safely append
to the previously masked document. A mask-session error is explicitly
`review_required`/failed; it is never silently replaced with generated PNG
layers.

For iterative review, the bridge exposes `POST /v1/photopea/sessions`,
`POST /v1/photopea/sessions/{id}/revisions`, and
`POST /v1/photopea/sessions/{id}/finalize`. The revision endpoint keeps one
Photopea browser session alive and requires matching source, checkpoint, and
parent revision hashes. Each revision returns a newly rebuilt editable
Photopea document and checkpoint; this is deliberately not described as
literal same-document mutation.

The Skill helper waits for the PSD stage by default. Use `--core-only` only for
diagnostics; that mode is not a complete print artifact and must be reported as
such.
