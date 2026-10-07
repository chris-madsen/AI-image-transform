# Code review: AI-image-transform — REQUEST CHANGES

**Дата:** 2026-10-07  
**Репозиторий:** <https://github.com/chris-madsen/AI-image-transform>  
**Проверенная ревизия:** [`5faef40`](https://github.com/chris-madsen/AI-image-transform/commit/5faef40f6b03872783852780459d7fb4951cab5e) (`master`)  
**Проверенный диапазон:** `0d4b8b6..5faef40` — четыре новых коммита, 49 файлов, `+8576/-446`

## Вердикт

**Изменения принимать нельзя.** Технический blocker создания linked raster mask в Photopea устранён, но заявленный workflow не реализован. Код по-прежнему принимает готовую `photopea_mask` снаружи, доверяет внешним vision-оценкам, не запускает production review-loop и не даёт vision-проверяющему ни одного изображения. При этом задачи 5.5 и 5.6 отмечены выполненными, а evidence matrix объявляет beauty-aware gate проверенным.

Это не мелкие недоделки. Это подмена архитектуры: вместо «система строит, показывает и исправляет маску» реализовано «клиент уже принёс финальные пиксели, а Photopea аккуратно упаковал их в PSD».

## Что реально стало лучше

- Bridge теперь действительно создаёт raster mask через Photopea Action Manager и проверяет PSD после повторного открытия.
- Передача source/mask сделана через `ArrayBuffer`, а не через URL с полным payload.
- Есть проверка пикселей маски, artwork и трёх garment-preview при round-trip.
- Добавлены hash-bound revision DTO и отдельный session API.
- Python suite проходит: **53 passed**. `node --check bridge/server.mjs` также проходит.

Это полезная инфраструктура. Но она проверяет только, что Photopea честно перенёс уже полученную маску. Она не доказывает, что маска правильная и что panther/reference workflow реализован.

## Блокирующие замечания

### P0-1. `photopea_mask` всё ещё является публичным authoritative input

Это прямо противоречит согласованному workflow.

- [`service.py:47–70`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/service.py#L47-L70) декодирует multipart `photopea_mask` отдельно от semantic masks и возвращает её как authoritative mask.
- [`service.py:116–119`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/service.py#L116-L119) передаёт её прямо в core processing.
- [`application.py:77–93`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/application.py#L77-L93) безусловно заменяет ей alpha и conservative, и artistic кандидатов.
- [`service.py:290–317`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/service.py#L290-L317) оставляет `photopea_mask` в публичном `/v1/jobs`.
- [`submit_artwork_job.py:47–66`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/skill/universal-image-matting/scripts/submit_artwork_job.py#L47-L66) заставляет агента загружать `--photopea-mask`.

Иными словами, плохие пиксели пантеры всё ещё рождаются до Photopea. Photopea лишь создаёт linked mask из готового carrier. Название `Photopea-authored mask` в таком коде вводит в заблуждение.

**Требование:** удалить `photopea_mask` из публичного job contract. Внешний клиент передаёт source, policy и при необходимости protected-reference/semantic hints. Pixel proposal создаёт внутренний vision/matting provider; Photopea создаёт из него реальную linked raster mask и является средой review/correction/finalization.

### P0-2. Специализированной segmentation/matting модели нет

[`ports.py:24–37`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/ports.py#L24-L37) содержит только `VisionProvider` Protocol. Production adapter отсутствует. В зависимостях и runtime нет BiRefNet, BEN2, SAM/SAM2, ViTMatte или другой модели, которая могла бы построить mask proposal.

LLM/VLM не должна рисовать полноразмерную alpha-маску по пикселям. Её роль — понять сцену, задать protected/removable regions, сравнить реальные previews с reference и принять или отклонить кандидат. Пиксельную сегментацию и matting должна выполнять специализированная модель.

**Требование:** реализовать хотя бы один настоящий `VisionProvider` adapter и выбрать модель по benchmark на целевых fixtures. Практичный старт:

1. BiRefNet/BEN2-класс модели — initial subject/background alpha.
2. SAM2-класс модели — promptable inclusion/exclusion для глаз, букв, листьев и выступающих деталей.
3. Matting/refinement stage — только для узкой uncertain edge band, без широкого полупрозрачного ореола.
4. Детерминированная композиция — protected reference имеет абсолютный приоритет; удаляется только edge-connected внешний фон.

Название конкретной модели не должно быть зашито в домен: нужен adapter + comparative fixture benchmark.

#### Обязательное ограничение: без платного API

Для этого проекта **не подключать PhotoRoom, BRIA API, fal.ai, Replicate или другой тарифицируемый per-image provider как обязательную часть pipeline**. В текущем репозитории никакой production `VisionProvider` пока вообще не подключён; платный provider обсуждается только как возможная будущая реализация. Он нам не нужен.

Рекомендуемый бесплатный стек:

1. **Основной production baseline — локальный `ZhengPeng7/BiRefNet_HR-matting`.** Код и weights опубликованы с MIT license; модель запускается локально и рассчитана на matting с input `2048×2048`. Она должна быть обёрнута внутренним `LocalBiRefNetProvider`, а не вызываться через внешний платный endpoint.
2. **Второй локальный кандидат — InSPyReNet.** Код/weights MIT; полезен как альтернативный proposal для сложных сцен и тонких структур. На наших fixtures надо сравнивать не рекламные картинки, а сохранность усов, букв, листьев и внутренних отверстий.
3. **Lucida v7 — только экспериментальный дополнительный кандидат.** Это локальный BiRefNet fine-tune, специально ориентированный на illustrations/print designs и имеющий готовый FastAPI server. Код и weights помечены MIT, но сам автор честно предупреждает о mixed/research-only licenses части training data и юридической неопределённости для коммерческого использования. Для Etsy нельзя молча объявлять его бесспорно безопасным; решение о production use должно быть зафиксировано отдельно.
4. **SAM2 + ViTMatte — необязательный correction path**, а не первая версия. Они локальные и open-source (SAM2 — Apache 2.0, ViTMatte — MIT), но требуют prompt/trimap orchestration и заметно усложняют pipeline.
5. **`rembg` допустим только как локальная ONNX-оболочка с явно указанной моделью**, например `birefnet-general`/`birefnet-general-lite`. Нельзя использовать его default вслепую: текущий default `bria-rmbg` имеет отдельную BRIA license и требует платного соглашения для коммерческого использования.

Стабильно бесплатного внешнего production API здесь рассчитывать не на что. Hugging Face даёт free user всего `$0.10` monthly inference credits; бесплатные Spaces/ZeroGPU имеют квоты, очереди и засыпают при простое. Это годится для ручного эксперимента, но не для job service и не должно становиться production dependency.

**Итоговое техническое решение:** поднять модель рядом с сервисом локально — Python/PyTorch или ONNX runtime, при необходимости как отдельный FastAPI container на `127.0.0.1`. На машине без GPU предусмотреть CPU mode (`birefnet-general-lite` для быстрого черновика), но не обещать скорость до benchmark. Деньги за каждый PNG не платятся; остаются только ресурсы собственного компьютера/сервера.

LLM/VLM также не должна быть обязательным платным pixel provider. На первом этапе visual acceptance можно делать детерминированными проверками плюс человеком по checkpoint previews. Если позднее нужен полностью автоматический reviewer, он должен быть отдельным локальным open-weight VLM adapter и всё равно не получает права напрямую рисовать authoritative alpha.

#### Решение под имеющееся железо

Доступны две машины: Linux-ноутбук с интегрированной Intel Iris и Windows-ПК с Intel i7, 64 GB RAM и Sapphire Radeon RX Vega 56 8 GB.

**Основной inference host — Windows-ПК с Vega 56.** Использовать native Windows `ONNX Runtime + DirectML`, а не ROCm. DirectML поддерживает DirectX 12 GPU начиная с AMD GCN 1st Gen; Vega 56 относится к GCN и должна определяться как `DmlExecutionProvider`. Современная официальная ROCm matrix ориентирована на Radeon 9000 и отдельные 7000 Series, поэтому Vega 56 там отсутствует. Не строить production на неофициальных ROCm hacks.

Приоритет реализации:

1. Отдельный Windows virtualenv.
2. `onnxruntime-directml` и фиксированный ONNX export модели.
3. Provider order: `DmlExecutionProvider`, затем `CPUExecutionProvider` как явный fallback.
4. Один inference request одновременно: DirectML session использует sequential execution и отключённый memory pattern.
5. Локальный FastAPI endpoint с model/version/provider/timing в каждом result manifest.
6. Linux service вызывает Windows endpoint только по домашней LAN; порт закрыт от публичного интернета и разрешён firewall только нужному хосту.

WSL2 с `torch-directml` технически возможен на Windows 11, но это public preview и добавляет ещё один слой проблем. Использовать его только как запасной эксперимент, если конкретный PyTorch model нельзя нормально экспортировать в ONNX. ROCm в WSL для Vega 56 не планировать.

**Intel Iris laptop — fallback/оркестратор.** OpenVINO умеет выполнять inference на Intel CPU и GPU. Сначала проверить `Core().available_devices`; если доступен `GPU`, benchmark ONNX/OpenVINO на нём, иначе использовать CPU. Эта машина подходит для core processing, Photopea bridge и небольших preview-resolution прогонов, но не надо заранее обещать acceptable full-size latency.

Vega 56 с 8 GB VRAM должна тестироваться на batch size 1 и фиксированном input 1024; затем попробовать 2048. Исходный master `4500×5400` не надо целиком заталкивать в сеть. Нужен global proposal на уменьшенной копии, возврат alpha к исходному размеру и локальный edge refinement с защитой глаз, усов, текста, листьев и внутренних отверстий. Если 2048 не помещается или нестабилен, это не blocker: остаётся 1024 proposal + refinement, либо CPU fallback с большим временем обработки.

### P0-3. Production «vision review loop» отсутствует

[`run_bounded_photopea_review()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/domain/photopea_review.py#L12-L60) вызывается только тестами. Production `ServiceRuntime` идёт напрямую в одноразовый [`psd_exporter.export()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/service.py#L144-L181). `PhotopeaSessionClient` существует, но production caller отсутствует.

Значит задача 5.6 «Add checkpoint/correction protocol and a bounded vision review loop» **не выполнена**. Написать чистую функцию и unit-тест к ней недостаточно; её надо включить в job pipeline.

**Требование:** production orchestration обязана делать `open session → fetch visual checkpoint → vision review → optional correction(s) → explicit accept → finalize`. Любое отсутствие review, timeout или exhausted revision budget переводит job в `review_required`, а не финализирует PSD.

### P0-4. Vision reviewer физически нечего проверять

[`checkpointSummary()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L787-L796) возвращает только идентификаторы и hashes. В checkpoint DTO тоже нет source, artwork, alpha mask, overlay или garment previews. Хотя bridge держит эти изображения в памяти, session API их не публикует.

Hash не является изображением. Нельзя оценить целостность головы, глаз, усов, букв, листвы, внутренних отверстий и ореола по SHA-256.

**Требование:** checkpoint должен предоставлять авторизованные immutable image endpoints или inline bytes для:

- source/reference;
- transparent artwork;
- grayscale alpha;
- alpha overlay/edge crop sheet;
- black, navy и blue-jean previews;
- protected-region crops и diff-map.

Review decision обязан быть привязан к `source_sha256 + revision_id + checkpoint_sha256`.

### P0-5. «Same-document correction» — неправда

[`startRevision()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L661-L684) выполняет:

```javascript
while (app.documents.length > 0) app.documents[0].close(...)
```

После этого source и mask пересылаются заново, а документ перестраивается. Это не коррекция того же документа и не сохранение editing context. Галочка 5.5 поставлена без оснований.

**Требование:** session хранит один открытый document. Revision должна менять pixels существующего `WORKING MASK`/linked layer mask внутри него, после чего bridge заново экспортирует checkpoints. Документ закрывается только после finalize/abort/expiry.

### P0-6. `RESTORED` и `WITH GAPS` — одинаковые близнецы

В initial build [`bridge/server.mjs:182–185`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L182-L185) и revision build [`bridge/server.mjs:390–393`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L390-L393) оба слоя дублируют один source и получают одну и ту же mask.

Никакого «restored artistic» против «conservative with gaps» нет. Названия слоёв изображают семантику, которой в пикселях не существует.

**Требование:** либо передавать два реально независимых кандидата/mask revisions, либо убрать ложные названия. Final choice должен делаться после visual review обоих кандидатов.

### P0-7. Finalize не требует решения `accepted`

[`POST /v1/photopea/sessions/:id/finalize`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L927-L938) проверяет авторизацию и round-trip pixels, но не требует signed review decision. Любой авторизованный клиент может открыть session и тут же финализировать текущий checkpoint.

**Требование:** finalize принимает одноразовый acceptance token/record, созданный только после successful visual review и привязанный к точному checkpoint. Revision должна инвалидировать предыдущее acceptance.

### P0-8. Контракт initial revision логически цикличен

[`models.py:442–474`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/domain/models.py#L442-L474) требует `checkpoint_sha256` в `photopea_mask_revision` ещё до запуска Photopea. Но checkpoint появляется только после того, как Photopea построит и экспортирует previews. Затем one-shot adapter требует, чтобы будущий evidence hash совпал с заранее переданным hash ([`photopea.py:94–132`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/adapters/photopea.py#L94-L132)).

Это chicken-and-egg contract. Тесты обходят проблему заранее подставленными константами; они не доказывают нормальный job flow.

**Требование:** initial proposal не содержит checkpoint hash. Bridge сам вычисляет первый checkpoint. Только correction/accept decision ссылаются на уже существующий checkpoint hash.

## Серьёзные замечания

### P1-1. `visual_quality` остаётся недоверенным пользовательским утверждением

[`models.py:476–506`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/domain/models.py#L476-L506) парсит присланные клиентом эстетические scores, а [`application.py:106–113`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/application.py#L106-L113) на их основе выбирает artistic candidate. Клиент может сам объявить свою работу качественной.

Эти оценки должны создаваться доверенным внутренним reviewer после просмотра checkpoint pixels, а не приходить в initial job policy.

### P1-2. Автоматические quality metrics не ловят дефектную пантеру

- [`_edge_fragmentation_score()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/domain/visual_quality.py#L23-L36) считает почти только изолированные foreground pixels. Большой вырванный кусок головы, уха или листвы может остаться связным и получить прекрасный score.
- [`_halo_score()`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/src/printify_artwork_cleaner/domain/validation.py#L14-L22) измеряет долю alpha `1..95` по площади холста. Это не измерение цветного fringe, серой каймы или DTG underbase glow.

Нужны topology/component retention, protected-region diffs, edge-band chroma contamination, distance-to-contour, dark-garment ΔE/underbase checks и visual comparison с approved reference.

### P1-3. Bridge не проверяет фактический source hash

Session/export API проверяет hash mask pixels, но `revision.source_sha256` просто принимается и затем копируется в evidence. В [`/v1/photopea/sessions`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L878-L898) и [`/v1/photopea/export`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/bridge/server.mjs#L948-L968) нет сравнения с SHA-256 реально загруженного source. Service path делает отдельную проверку, но прямой bridge contract остаётся ложноположительным.

### P1-4. Job публикует PNG до Photopea, а после review возвращает только PSD

Core artifacts создаются и публикуются до deferred Photopea export. После Photopea `_run_deferred_psd()` добавляет только `artwork_editable.psd`; accepted artwork/mask/previews из финального checkpoint не становятся job artifacts. Поэтому утверждение «PNG и PSD относятся к одной принятой revision» не обеспечено единым источником истины.

### P1-5. Пятиминутный budget практически исчерпан одним full-size round-trip

Evidence matrix заявляет `232.39 s` для одного `4500×5400` direct session/export. При TTL/budget 300 s остаётся около 68 s на загрузку, vision review, corrections и finalize. Несколько revisions в этот budget реалистично не помещаются.

Нужны раздельные бюджеты стадий, preview-resolution checkpoints для review и только один full-resolution finalize, либо документированное увеличение SLA.

## Документация и процесс

### Задачи отмечены выполненными раньше факта

[`tasks.md:37–41`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/openspec/changes/correct-core-processing-semantics/tasks.md#L37-L41) отмечает 5.2, 5.3, 5.5 и 5.6 выполненными. По результатам ревью:

- 5.2/5.3 — частично подтверждены техническим round-trip, но не end-to-end job evidence;
- 5.5 — не выполнена: revision закрывает документ и строит новый;
- 5.6 — не выполнена: loop не подключён к production, reviewer не получает pixels, finalize не требует acceptance;
- 5.4 корректно оставлена незавершённой.

Фактический прогресс не `26/27`. Галочки 5.5 и 5.6 надо снять; 5.2/5.3 оставить только после воспроизводимого evidence либо явно пометить scope как bridge-only.

### Evidence matrix переоценивает доказательства

[`requirements-evidence.md`](https://github.com/chris-madsen/AI-image-transform/blob/5faef40f6b03872783852780459d7fb4951cab5e/docs/domain/requirements-evidence.md) содержит несколько проблем:

- строка 14 называет beauty-aware gate verified, хотя production reviewer отсутствует;
- строка 17 всё ещё говорит о 32 тестах, а сейчас их 53;
- строка 23 ссылается на `artifacts/photopea-full-smoke-20261006/`, которого нет в GitHub.

PSD действительно не надо коммитить — это было отдельное указание. Но тогда evidence row должен честно говорить «local/unpublished evidence» и содержать воспроизводимую команду, manifest, hashes, размеры, тайминги и лог. Нельзя ссылаться на отсутствующий repo path как на доступное доказательство.

### OpenSpec/SDD skills присутствуют, но их guardrails не соблюдены

В `.agents/skills/` лежат generated OpenSpec skills. По Git history невозможно доказать, запускал ли их агент. Но результат противоречит `openspec-apply-change` guardrails: обнаруженные design gaps не были вынесены на согласование, а tasks отмечены выполненными до production implementation/evidence.

Дополнительно:

- `openspec` CLI в проверочном окружении отсутствует, поэтому заявления о strict validation мной независимо не подтверждены;
- `git diff --check 0d4b8b6..5faef40` **не проходит**: conversation dumps содержат множество trailing spaces и лишнюю пустую строку в EOF;
- bridge имеет только syntax script (`node --check`), но не автоматический behavioral/integration suite.

## Как переделать нормально

### Правильный runtime flow

1. `POST /v1/jobs`: source + frozen policy + optional protected reference/semantic hints. Никакой публичной final mask и никаких self-reported quality scores.
2. Внутренний vision adapter строит `MaskCandidateBundle`: conservative alpha, optional restored alpha, uncertainty, protected regions, provenance/model version.
3. Детерминированный core применяет protected-reference precedence и запрещает удаление alpha вне разрешённого edge-connected background.
4. Bridge открывает source **один раз**, создаёт один документ, импортирует proposal как `WORKING MASK` и создаёт linked raster masks внутри Photopea.
5. Bridge экспортирует visual checkpoint assets. Vision reviewer действительно получает pixels/reference и возвращает typed `accept` либо correction.
6. Correction применяется к существующему mask/document; после неё создаётся новый checkpoint и старое acceptance инвалидируется.
7. После explicit accept Photopea экспортирует final PNG, alpha/mask, previews и PSD из одного checkpoint.
8. Service публикует единый artifact bundle с общей `accepted_revision_id`, source hash, pixel hash, PNG file hash и PSD round-trip evidence.

### Минимальный новый контракт

```text
JobInput
  source
  policy
  protected_reference?
  semantic_hints?

MaskProposal (internal)
  revision_id
  source_sha256
  conservative_mask
  restored_mask?
  uncertainty
  provenance { provider, model, version }

PhotopeaCheckpoint
  revision_id
  source_sha256
  checkpoint_sha256
  assets { source, artwork, mask, overlay, black, navy, blue_jean, protected_diff }

ReviewDecision
  source_sha256
  checkpoint_sha256
  accepted
  correction_mask_or_patch?
  reviewer/model/version/confidence
```

Initial proposal не должен содержать `checkpoint_sha256`: его ещё не существует. Этот hash появляется только в `PhotopeaCheckpoint` и используется следующей correction/accept operation.

## Обязательные acceptance tests перед следующей галочкой

1. Реальный `/v1/jobs → poll → accepted visual review → PNG + PSD` через настоящий bridge, не mock.
2. Panther regression fixture: глаза, уши, нос, усы, буквы, листья справа от морды, перекрывающая тело растительность и внутренние отверстия сохранены относительно approved reference.
3. Тест доказывает, что reviewer получил и открыл фактические source/mask/previews, а не только hashes.
4. Тест отклоняет finalize без acceptance текущего checkpoint.
5. Тест доказывает, что correction не закрывает и не пересоздаёт Photopea document.
6. Тест доказывает, что conservative и restored различаются там, где это ожидается, и оба отдельно валидируются.
7. Тест с ложным высоким `visual_quality` от клиента не может перевести job в `passed`.
8. Source hash bridge-а сверяется с реально загруженными bytes.
9. Full-size test укладывается в честный end-to-end SLA с review, а не только в isolated export.
10. Evidence matrix генерируется из CI outputs или содержит полностью воспроизводимый внешний manifest.

## Итоговое сообщение автору

Ты починил важную низкоуровневую часть — Photopea теперь действительно создаёт linked raster mask и делает pixel round-trip. Но ты снова закрыл техническую подзадачу и объявил выполненной пользовательскую функцию целиком. Система всё ещё не умеет сама получить хорошую пантеру: она принимает чужую готовую mask, не запускает vision review, не показывает reviewer-у изображения и позволяет финализировать без принятия результата. Названия классов, hashes и зелёные unit-тесты не заменяют рабочий end-to-end контур.

Сними необоснованные галочки, перестань называть внешний carrier «Photopea-authored mask», подключи реальный vision/matting provider и production review loop, дай reviewer-у реальные pixels и только после этого возвращайся с evidence.
