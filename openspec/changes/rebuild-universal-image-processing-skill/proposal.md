# Proposal

## Why

Текущий проект является benchmark-скриптами, а не устойчивым продуктом обработки artwork: в нём нет frozen policy, жизненного цикла job, безопасного отказа, review-статусов и единого контракта артефактов. Сейчас нужен новый доменный контур, чтобы ChatGPT Skill мог передавать структурированное намерение локальному сервису, а сервис — детерминированно обрабатывать изображение без перерисовки исходного RGB.

## What Changes

- **BREAKING**: заменить benchmark-first entrypoint на domain-first pipeline обработки artwork.
- Добавить frozen `ProcessingPolicy`, inspection отчёт, protected regions и явные статусы `accepted`, `running`, `review_required`, `passed`, `refused`, `failed`.
- Добавить асинхронный job API для Skill: создание job, polling статуса, список и скачивание артефактов.
- Реализовать функциональное ядро инспекции, edge-connected mask, alpha rendering, binary/soft/halftone варианты, preview и validation.
- Запретить генеративную перерисовку, скрытые fallback-модели и перезапись исходника.
- Создавать PNG, mask, alpha-mask, printer-aware previews и JSON report; layered PSD получать через Photopea Live API.
- Добавить structured JSON events/logs, correlation/job identifiers и базовые RED/domain metrics.
- Оставить GPT интерпретатором пользовательского текста на стороне Skill; image service принимает только валидированную structured policy.
- Сделать Photopea Live bridge обязательным adapter для выдачи `passed` job с PSD; обработка PNG/mask может диагностически завершаться без него только как `review_required`.
- Исключить из продукта Printify upload, Etsy/store workflow, MCP и управление Photopea мышью.

## Capabilities

### New Capabilities

- `agent-job-contract`: асинхронный контракт job, idempotency, статусы и artifact discovery для Skill.
- `artwork-inspection`: нормализация исходника, alpha/RGB inspection, edge classification и crop-risk detection.
- `semantic-policy-and-protection`: frozen ProcessingPolicy, protected regions и безопасная передача semantic intent.
- `mask-composition`: построение и версионирование масок с edge connectivity, protected areas и uncertainty.
- `print-safe-rendering`: alpha-only rendering, premultiplied resize, binary/soft/halftone стратегии и DTG-aware previews.
- `review-and-validation`: halo/frame/detail checks, acceptance decisions и безопасный отказ.
- `artifact-export`: immutable artifact bundle, JSON report и layered PSD, экспортированный через Photopea.
- `photopea-adapter`: outer-environment bridge, Photopea Live Messaging и сохранение PSD/PNG обратно в artifact store.

### Modified Capabilities

Нет: существующих capability specs в проекте не было.

## Impact

- Новые доменные модули появятся в `src/printify_artwork_cleaner/`.
- Появится FastAPI/uvicorn service adapter и локальный filesystem job/artifact store.
- Появятся Skill instructions и helper script для формирования policy и вызова сервиса.
- `pyproject.toml` получит runtime-зависимости для HTTP, PSD, multipart и metrics.
- Текущие benchmark-модули сохраняются как исследовательские fixtures, но не являются доменным API.
- Named Cloudflare Tunnel и bearer secret остаются deployment-инфраструктурой и не попадают в domain core.
