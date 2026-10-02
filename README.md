# Printify Artwork Cleaner

Domain-first is a local service for cleaning artwork before printing production.
The service saves the original RGB, changes only alpha/mask, creates print-safe
variants, previews, JSON report and editable PSD via Photopea Live API.
## Quick start

```bash
uv sync --extra dev
make test
openspec validate rebuild-universal-image-processing-skill --type change --strict
```

Service initiation
```bash
make service
```

The service accepts asynchronous jobs via `post /v1/jobs`. Full Skill contract
located in `skill/universal-image-matting/SKILL.md`, API and local launch — in
`docs/deployment/local-service.md`.
## Photopea PSD export

The PSD is not created by the Python library. Image service calls a separate
`PhotopeaLiveApiAdapter` that transfers images to the external environment with
Photopea iframe via Live Messaging API. Photopea returns PSD via
`app.activeDocument.saveToOE("psd:true")`.
Starting the Adapter
```bash
cd bridge
npm install
npx playwright install chromium
PHOTOPEA_LIVE_API_TOKEN=change-me npm start
```

Without an available Photopea Live adapter job is not considered successfully completed and
gets` review_required `.
## Project structure

- `src/printify_artwork_cleaner/domain/` — pure domain core.
- `src/printify_artwork_cleaner/application.py` — processing use case.
- `src/printify_artwork_cleaner/adapters/` — filesystem and Photopea adapters.
- `src/printify_artwork_cleaner/service.py` — FastAPI imperative shell.
- `bridge/` — Photopea Live API outer-environment adapter.
- `openspec/` — proposal, specs, design and implementation checklist.
- `docs/domain/` — DDD ubiquitous language and event storming.

## Git publication

Copy `.env.example` to local `.env`; real tokens are not committed.
Before publishing, perform `make test`, `make bridge-check` and
`make openspec-validate`.