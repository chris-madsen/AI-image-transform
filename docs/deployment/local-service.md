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
make service
```

Without this bridge the service may preserve diagnostic PNG/mask artifacts,
but it MUST return `review_required` rather than claiming a completed PSD job.
