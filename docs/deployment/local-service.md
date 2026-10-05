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

Core PNG, mask and preview artifacts are produced before the Photopea adapter
is scheduled. PSD export runs in a separate background executor and updates the
same job when it completes; clients can download the core artifacts while PSD
is pending. The adapter has a hard five-minute timeout. Without a completed
Photopea export the service MUST return `review_required` rather than claiming
a completed PSD job.

The Photopea session uses a raster mask carrier and canonical charID mask
creation; polygon selection plans are rejected. Until the same-document
checkpoint and pixel round-trip fixture passes against the deployed Photopea
runtime, a mask-session error is explicitly `review_required`/failed; it is
never silently replaced with generated PNG layers.

For iterative review, the bridge exposes `POST /v1/photopea/sessions`,
`POST /v1/photopea/sessions/{id}/revisions`, and
`POST /v1/photopea/sessions/{id}/finalize`. The revision endpoint keeps one
Photopea document alive and requires matching source, checkpoint, and parent
revision hashes.

The Skill helper waits for the PSD stage by default. Use `--core-only` only for
diagnostics; that mode is not a complete print artifact and must be reported as
such.
