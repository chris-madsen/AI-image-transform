# Design

## Context

Текущий репозиторий содержит исследовательский benchmark с alpha-only image operations и optional ML backends. OpenSpec change вводит отдельный runtime-контур, который должен принимать artwork и frozen policy, выполнять processing pipeline и возвращать immutable artifact bundle. Product requirements находятся в `docs/Printify_Artwork_Cleaner_PRD.md`.

Ограничения:

- исходный visible RGB является источником истины;
- domain core не должен знать о HTTP, filesystem, model SDK, Photopea или Cloudflare;
- отсутствие AI/model dependency не должно приводить к скрытому fallback;
- Printify upload, Etsy и MCP не являются частью runtime;
- длительная обработка требует async job lifecycle;
- images могут содержать приватные пользовательские данные, поэтому logs не должны содержать raw image bytes, tokens или policy secrets.

## Goals / Non-Goals

**Goals:**

- Реализовать functional core для inspection, policy freeze, mask composition, alpha rendering, previews и validation.
- Добавить imperative shell с async HTTP API, filesystem artifact store и structured events.
- Отделить Skill/agent adapter от processing service через versioned JSON contract.
- Формировать проверяемый layered PSD, PNG variants, masks, previews и JSON report.
- Сделать review-required/refused first-class результатами.
- Подготовить DDD event-storming artifacts для последующего уточнения bounded contexts.

**Non-Goals:**

- Автоматический upload в Printify или управление магазином.
- Реализация автоматического Photopea Live bridge является частью MVP PSD pipeline.
- Обучение собственной segmentation model.
- Генеративная дорисовка или изменение исходного дизайна.
- Распределённая очередь и production multi-node deployment на первом шаге.

## Decisions

### D1. Domain-first package вместо расширения benchmark

Новый package `printify_artwork_cleaner` содержит ADTs, pure functions и application orchestration. Исследовательские benchmark-модули не входят в публикуемый runtime и не являются domain API.

**Alternative rejected:** продолжать добавлять flags в benchmark scripts. Это сохраняет неявное состояние, не даёт job contract и смешивает исследование с product behavior.

### D2. Frozen boundary и Result-based failures

На входной границе source bytes и policy нормализуются один раз. Domain failures представлены structured errors; исключения остаются для повреждённого runtime и unexpected bugs.

Основные immutable values: `ProcessingPolicy`, `ArtworkInspection`, `MaskRevision`, `ValidationResult`, `ArtifactManifest`.

### D3. Async HTTP shell

FastAPI/uvicorn предоставляет:

```text
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/artifacts
GET  /v1/artifacts/{artifact_id}
GET  /healthz
GET  /metrics
```

`POST` принимает multipart source и JSON manifest/policy, возвращает `202`. Внутренний bounded executor запускает pipeline; job store хранит status и manifest на filesystem. API не блокирует HTTP request до окончания ML/PSD работы.

**Alternative rejected:** synchronous endpoint. Большие изображения и model initialization могут превысить HTTP timeout и делают retry semantics небезопасным.

### D4. Ports at the imperative shell

Core получает зависимости через ports:

- `VisionProvider` — optional semantic mask/confidence;
- `ArtifactStore` — immutable source и output files;
- `JobStore` — status, idempotency и progress;
- `PsdExporter` — layered PSD;
- `PreviewRenderer` — background compositing;
- `Clock` и `IdGenerator` — deterministic tests;
- `PhotopeaLiveApiAdapter` — обязательный adapter для `passed` результата с PSD.

Default MVP adapters: local filesystem, deterministic edge mask, local thread executor, Photopea Live PSD exporter, Pillow/NumPy previews. Bridge-unavailable path is explicit `review_required`/`failed`.

### D5. Deterministic edge mask as safe baseline

Для MVP внешний фон определяется edge-connected flood fill с bounded color tolerance и source-alpha preservation. Внутренние похожие цвета не удаляются. Semantic provider может добавить candidate/protected regions, но не может самовольно перезаписать source RGB.

### D6. Printer-aware rendering is a validation policy

Каждый candidate проходит background previews. Для dark garment continuous partial alpha не принимается при обнаружении halo score выше policy threshold. Binary/halftone variants изменяют только alpha. Halftone screen должен быть детерминированным по seed и параметрам.

### D7. PSD export through Photopea Live API

PSD создаётся отдельным `PhotopeaLiveApiAdapter` adapter, а не Python PSD writer. Image service передаёт bridge candidate PNG/mask и job metadata. Outer environment загружает Photopea iframe, отправляет ArrayBuffer и JavaScript через Web Messaging, создаёт layers и вызывает `app.activeDocument.saveToOE("psd:true")`. Bridge возвращает PSD bytes в artifact store.

Минимальная структура PSD: source backup, working art, working mask, black/white/gray/navy/blue-jean test layers. Interoperability test проверяет canvas/layer names и merged preview после открытия результата.

**Alternative rejected:** `psd-tools`/`pytoshop` local writer. Они создают PSD вне Photopea и не гарантируют тот же document/layer behavior, который нужен для ручного workflow пользователя.

### D8. Skill is an agent adapter, not a second domain engine

Skill должен:

1. собрать natural-language intent от GPT;
2. сформировать schema-valid `ProcessingPolicy`;
3. отправить source + policy в service;
4. poll job;
5. вернуть artifact links и report.

Он не должен копировать алгоритм маски и не должен повторно интерпретировать report.

### D9. Observability contract

Каждый request и domain event содержит `correlation_id`, `job_id`, `event_type` и `pipeline_version`. Логи — JSONL с redaction. Metrics:

- `artwork_jobs_total{status}`;
- `artwork_job_duration_seconds`;
- `artwork_job_queue_depth`;
- `artwork_validation_total{decision}`;
- `artwork_artifacts_total{media_type}`;
- `artwork_http_requests_total{method,route,status}`.

Не допускаются labels с image name, user text, source hash или arbitrary job id.

### D10. Retention and security

Local artifact store использует job-scoped directories, bearer secret из environment и TTL cleanup для завершённых jobs. Source bytes, tokens и policy text не пишутся в обычный log. Cloudflare Tunnel — deployment concern, а не domain dependency.

## DDD / Event Storming Model

Bounded contexts:

1. Agent Job — submission, lifecycle, idempotency.
2. Artwork Inspection — source facts and risk classification.
3. Semantic Policy — intent and protected details.
4. Mask Composition — mask revisions and uncertainty.
5. Print-safe Rendering — alpha variants and previews.
6. Review & Validation — decisions and review regions.
7. Artifact Packaging — immutable downloadable bundle.
8. Photopea Integration — mandatory PSD export bridge and optional manual editing surface.

Candidate commands: `SubmitProcessingJob`, `InspectArtwork`, `ResolvePolicy`, `BuildMask`, `RenderCandidate`, `ValidateCandidate`, `RequestReview`, `PackageArtifacts`, `GetArtifacts`.

Candidate domain events: `JobAccepted`, `SourceFrozen`, `ArtworkInspected`, `PolicyFrozen`, `MaskProposed`, `MaskRevisionCreated`, `CandidateRendered`, `PreviewGenerated`, `ValidationCompleted`, `ReviewRequired`, `ArtifactsPackaged`, `JobFailed`.

Event-storming output must be stored in `docs/domain/` and then reconciled with this design before implementation tasks are marked complete.

## Risks / Trade-offs

- [Risk] Edge-connected color flood fill can remove a same-colored foreground region → [Mitigation] protected regions, conservative tolerance, crop-risk detection and review status.
- [Risk] PSD writer may produce a file that opens differently in Photopea → [Mitigation] fixture-based layer/canvas round-trip and manual Photopea interoperability check.
- [Risk] Cloudflare tunnel or local service unavailable → [Mitigation] explicit transport error in Skill; no pretending that a job passed.
- [Risk] AI provider changes mask semantics → [Mitigation] provider contract, model/version in report, source RGB invariant and golden tests.
- [Risk] Async filesystem store is not horizontally scalable → [Mitigation] keep `JobStore`/`ArtifactStore` ports and defer distributed store to a separate change.
- [Risk] High-cardinality observability labels leak data → [Mitigation] fixed label sets and redaction tests.

## Migration Plan

1. Generate and validate OpenSpec artifacts.
2. Add domain package and pure tests without removing benchmark modules.
3. Add local service and run it against fixture images.
4. Add Skill adapter and local integration test.
5. Add DDD event-storming documents and reconcile terminology.
6. Make the new service the documented entrypoint; retain benchmark commands for research.
7. Add Cloudflare deployment documentation only after local contract tests pass.

Rollback is file-level: disable the new service/Skill entrypoint and continue using existing benchmark scripts; no existing artifact or source file is overwritten.
