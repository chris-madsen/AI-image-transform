# Printify Artwork Cleaner

Domain-first локальный сервис для очистки artwork перед print production.
Сервис сохраняет исходный RGB, изменяет только alpha/mask, создаёт print-safe
варианты, previews, JSON report и editable PSD через Photopea Live API.

## Quick start

```bash
uv sync --extra dev
make test
openspec validate rebuild-universal-image-processing-skill --type change --strict
```

Запуск сервиса:

```bash
make service
```

Сервис принимает асинхронные jobs через `POST /v1/jobs`. Полный контракт Skill
находится в `skill/universal-image-matting/SKILL.md`, API и локальный запуск — в
`docs/deployment/local-service.md`.

## Photopea PSD export

PSD не создаётся Python-библиотекой. Image service вызывает отдельный
`PhotopeaLiveApiAdapter`, который передаёт изображения во внешний environment с
Photopea iframe через Live Messaging API. Photopea возвращает PSD через
`app.activeDocument.saveToOE("psd:true")`.

Запуск адаптера:

```bash
cd bridge
npm install
npx playwright install chromium
PHOTOPEA_LIVE_API_TOKEN=change-me npm start
```

Без доступного Photopea Live adapter job не считается успешно завершённым и
получает `review_required`.

## Project structure

- `src/printify_artwork_cleaner/domain/` — pure domain core.
- `src/printify_artwork_cleaner/application.py` — processing use case.
- `src/printify_artwork_cleaner/adapters/` — filesystem and Photopea adapters.
- `src/printify_artwork_cleaner/service.py` — FastAPI imperative shell.
- `bridge/` — Photopea Live API outer-environment adapter.
- `openspec/` — proposal, specs, design and implementation checklist.
- `docs/domain/` — DDD ubiquitous language and event storming.

## Git publication

Скопируйте `.env.example` в локальный `.env`; реальные токены не коммитятся.
Перед публикацией выполните `make test`, `make bridge-check` и
`make openspec-validate`.
