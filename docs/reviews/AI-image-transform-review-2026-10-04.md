# Review: AI-image-transform / Photopea mask pipeline

**Дата:** 2026-10-04  
**Ревизия:** `f25adc9` (`Documentation updated`)  
**Репозиторий:** <https://github.com/chris-madsen/AI-image-transform>  
**Вердикт:** merge / acceptance пока блокировать. Детерминированное Python-ядро стало заметно безопаснее, но заявленный Photopea workflow не реализован сквозным образом. Нынешний one-source путь гарантированно падает до создания PSD, а после локального исправления polygon action всё равно останутся более серьёзные смысловые расхождения: нет итеративного vision-loop, PNG и PSD строятся из разных масок, а «round-trip verified» проверяет почти только имена слоёв.

## Что проверено

- Полный текущий код, OpenSpec changes, PRD, Skill helper и transcript проблемы.
- `uv run --extra dev pytest -q`: **46 passed**, одно предупреждение Starlette.
- `node --check bridge/server.mjs`: проходит.
- `git diff --check`: проходит.
- OpenSpec CLI в окружении отсутствует, поэтому заявления о strict validation независимо не воспроизводились.
- Официальные материалы Photopea: [Live Messaging](https://www.photopea.com/api/live), [Scripts](https://www.photopea.com/learn/scripts), [Masks](https://www.photopea.com/learn/masks), issue [photopea/photopea#5902](https://github.com/photopea/photopea/issues/5902).
- В Photopea API Playground отдельно воспроизведено: создание raster mask через canonical charID Action Manager работает; проблемным является построение polygon selection, а не raster mask как таковая.

## Находки по приоритету

### P0 — one-source Photopea path сейчас не может выпустить PSD

`photopeaMaskSessionScript()` строит каждое выделение через stringID Action Manager (`set` / `addTo` / `subtractFrom`, `channel`, `selection`, `polygon`, `points`) и зависает либо падает именно на этом вызове: [`bridge/server.mjs:198-216`](https://github.com/chris-madsen/AI-image-transform/blob/f25adc9/bridge/server.mjs#L198-L216). Следующие операции — создание mask channel, слоёв и `saveToOE()` — не выполняются.

Issue #5902 не доказывает невозможность создания маски. Он описывает исключение в `doc.selection.select()` в 2023 году. Он ничего не гарантирует про текущую самодельную схему ActionDescriptor и не относится к созданию raster mask через канал. Более того, canonical charID sequence уже работает:

```javascript
function c(id) { return charIDToTypeID(id); }

function selectActiveLayerTransparency() {
  var d = new ActionDescriptor();
  var selection = new ActionReference();
  var transparency = new ActionReference();
  selection.putProperty(c("Chnl"), c("fsel"));
  transparency.putEnumerated(c("Chnl"), c("Chnl"), c("Trsp"));
  d.putReference(c("null"), selection);
  d.putReference(c("T   "), transparency);
  executeAction(c("setd"), d, DialogModes.NO);
}

function addRevealSelectionMask() {
  var d = new ActionDescriptor();
  var at = new ActionReference();
  d.putClass(c("Nw  "), c("Chnl"));
  at.putEnumerated(c("Chnl"), c("Chnl"), c("Msk "));
  d.putReference(c("At  "), at);
  d.putEnumerated(c("Usng"), c("UsrM"), c("RvlS"));
  executeAction(c("Mk  "), d, DialogModes.NO);
}
```

Это не UI-костыль: Live API официально принимает `ArrayBuffer` и исполняет script strings, а raster mask в Photopea по определению является grayscale pixel image. Правильный перенос результата vision — raster mask, не тысячи polygon points.

### P0 — обещанного checkpoint → vision review → correction loop нет

PRD описывает сеанс `source → typed mask plan → Photopea checkpoint → vision review → typed correction → checkpoint`, но фактический endpoint:

1. запускает новый Chromium;
2. открывает source;
3. исполняет один заранее переданный plan;
4. сохраняет PSD;
5. закрывает браузер.

`VisionProvider.review_photopea_checkpoint()` существует только как Protocol (`src/printify_artwork_cleaner/ports.py:25-38`); реализации и вызова нет. `PhotopeaCheckpoint` содержит только три строки, но не mask preview, transparent artwork и garment previews. Нет endpoint/state machine для следующей revision, нет parent revision, нет bounded retry loop, нет сохранённого сеанса. Поэтому tasks 5.5–5.6 и соответствующие формулировки PRD пока являются дизайном, не реализацией.

### P0 — официальный PNG и PSD создаются из разных источников истины

Core сначала создаёт `artwork_conservative.png`, `artwork_artistic.png` и их alpha из `ResolvedMaskBundle` и perimeter algorithm (`application.py:61-138`). Затем deferred PSD path сознательно **не использует** эти кандидаты: передаёт в Photopea исходник и отдельный `photopea_mask_plan`, а вместо выбранного artwork/mask подставляет source RGBA и source alpha ([`service.py:141-165`](https://github.com/chris-madsen/AI-image-transform/blob/f25adc9/src/printify_artwork_cleaner/service.py#L141-L165)).

Следствие: даже успешный PSD может визуально не совпасть с выданным PNG. Никакой hash/equivalence check не связывает:

- `ResolvedMaskBundle`;
- `MaskTuning`;
- `VisualQualityAssessment`;
- `PhotopeaMaskPlan`;
- финальные PNG/PSD.

Это архитектурный дефект, а не недостающий тест. Финальный PNG следует экспортировать **из того же принятого Photopea document/revision**, из которого сохранён PSD. Python candidate можно оставить preflight/initial proposal, но не вторым независимым финальным результатом.

### P1 — `X-Photopea-Roundtrip: verified` даёт ложное ощущение conformance

После повторного открытия PSD `photopeaRoundTripScript()` проверяет только наличие слоёв по именам и возможность выбрать mask channel ([`bridge/server.mjs:344-400`](https://github.com/chris-madsen/AI-image-transform/blob/f25adc9/bridge/server.mjs#L344-L400)). Он не проверяет:

- что source/art/mask layers непустые;
- реальные пиксели mask channel;
- равенство linked mask утверждённой alpha mask;
- RGB кандидатов;
- тип и содержимое garment fill layers;
- рендер на black/navy/blue-jean;
- отсутствие halo и потерянных protected pixels.

Тем не менее bridge ставит header `verified` (`bridge/server.mjs:604`), Python adapter слепо превращает его в `round_trip_verified=True`, а service выставляет `psd_validation_status=passed` (`service.py:173-204`). Это нарушает собственный PRD §15.

Тест `test_photopea_round_trip_capability_marks_exact_payload_verified` также не является round-trip test: fake exporter возвращает `b"8BPS" + b"round-tripped-payload"`. `test_photopea_session_sends_only_source_and_typed_plan` доверяет подставному HTTP header. Эти тесты полезны как contract tests, но не как evidence реального PSD conformance.

### P1 — polygon plan семантически не подходит к задаче

Даже если подобрать working ActionDescriptor, `subject_polygons/remove_polygons/protect_polygons` не выражают то, что требуется продукту:

- мех, волосы, усы, трава и дым;
- отверстия букв и сложную топологию;
- частичную alpha 0…255;
- локальную коррекцию halo на уровне пикселей;
- сохранение тонких disconnected details.

Feather одного полигона не заменяет маттинг. При лимитах 128 × 4096 points descriptor может стать огромным, но всё равно останется плохой аппроксимацией raster mask. Для этой задачи raster mask/delta — доменный тип, polygon может остаться лишь опциональной coarse ROI-подсказкой.

### P1 — решения vision не привязаны криптографически к проверяемому артефакту

`VisualQualityAssessment.reference_id`, `MaskTuning.decision_id` и `PhotopeaMaskPlan.revision_id` — произвольные строки. В моделях нет обязательных `source_sha256`, `parent_revision_id`, `input_mask_sha256`, `checkpoint_sha256` и `result_mask_sha256`. Поэтому корректная оценка или plan от изображения A может быть повторно отправлена с изображением B и формально пройти ingest.

Нужно запретить такую переносимость на уровне schema, а не соглашением об именовании ID.

### P1 — Skill helper нарушает заявленную обязательность PSD

Skill говорит скачивать core artifacts и **не ждать Photopea**, если пользователь отдельно не запросил PSD (`skill/universal-image-matting/SKILL.md:22-27`). Helper прекращает polling при `psd_export_status=pending`, если не указан `--wait-for-psd` (`submit_artwork_job.py:74-76`). OpenSpec task 4.5 отмечает это выполненным.

Это расходится с уточнённым требованием: данный skill должен завершать полный PNG + editable PSD workflow; для PNG-only должен использоваться другой путь. Правильнее сделать ожидание PSD default, а отдельный `--core-only` — явным opt-out, если такой режим вообще разрешён продуктом. Core artifacts можно публиковать рано, но job не должен становиться terminal-success для этого skill до PSD validation.

### P1 — bridge сам создаёт лишние memory copies и тяжёлые raster layers

На входе `Buffer` превращается в обычный JS array чисел (`Array.from(files[index].buffer)`), затем обратно в `Uint8Array`. На выходе каждый 4 MiB chunk снова превращается в `Array<number>` ([`bridge/server.mjs:432-472, 492-518`](https://github.com/chris-madsen/AI-image-transform/blob/f25adc9/bridge/server.mjs#L432-L518)). Для production artwork это многократная сериализация с большим overhead по памяти и GC.

Кроме того, «COLOR FILL» создаются как пять full-canvas raster `artLayers`, а не Solid Color Fill content layers (`bridge/server.mjs:274-329`). Это пять лишних полноразмерных bitmap и одна вероятная причина GPU/RAM pressure.

Нормальный transport: временные tokenized `/blob/:id` endpoints. Outer page делает `fetch(...).arrayBuffer()` и передаёт buffer в iframe как transferable. Ответный ArrayBuffer outer page отправляет обратно bridge через `fetch(..., {method: "POST", body: buffer})`. Так Node↔page boundary не сериализует миллионы чисел. Для garment previews использовать реальные Solid Color Fill layers либо один переиспользуемый fill для checkpoint renders.

### P1 — evidence matrix и task status местами завышены

- `correct-core.../tasks.md` помечает 5.2 complete, хотя текущий one-source path PSD не создаёт.
- Evidence matrix называет garment fills «Verified on fixture», но reopen проверяет только имена; сами слои — raster layers.
- Восемь «golden classes» не имеют golden expected outputs: тест игнорирует переменную `allowed` и для всех случаев утверждает один результат `REVIEW_REQUIRED` (`tests/test_golden_cleaner.py:27-68`). Это safety smoke matrix, а не golden acceptance suite.
- Реального full-resolution POST → poll → Photopea → reopen → pixel compare теста нет; это честно отражено в части unchecked tasks, но противоречит некоторым `Verified` формулировкам.

5.2 следует вернуть в unchecked до появления artifact evidence. 5.3–5.6 справедливо оставить unchecked.

### P2 — автоматические visual metrics слишком слабы для названий, которые им даны

- `halo_score` — доля всех canvas pixels с alpha 1…95. Он не измеряет цвет каймы, ширину внешнего halo или DTG underbase; маленькая, но яркая кайма может пройти, а намеренный дым — упасть.
- `fragmentation_score` считает почти только изолированные foreground pixels с ≤1 neighbour. Рваный контур, потерянные усы или срезанные буквы могут получить высокий score.
- Background reference — одна median border color и 4-connectivity. Многоцветный/градиентный border и diagonal connectivity обрабатываются ненадёжно.

Это допустимые guardrails, но не «beauty-aware verification». Нужен image-conditioned vision review плюс topology/edge-band metrics; названия и evidence должны оставаться скромнее до появления таких тестов.

### P2 — исходный PRD был существенно сокращён

Первоначальный PRD содержит 631–632 строки; после `docs: standardize repository language to English` осталось 209, текущая версия восстановлена лишь до 365. Потеряны use cases, значительная часть FR/NFR, manual Photopea reference workflow, risk table, phases и open questions. Для проекта, где «весь контекст» является частью задания, это governance regression.

Лучше восстановить полный PRD как baseline и вносить изменения отдельным amendment/delta с traceability, а не заменять документ сокращённым пересказом.

## Как исправить Photopea workflow нормально

### 1. Заменить polygon contract на raster revision contract

Минимальный typed payload:

```json
{
  "revision_id": "mask-r2",
  "parent_revision_id": "mask-r1",
  "source_sha256": "...",
  "checkpoint_sha256": "...",
  "base_mask_sha256": "...",
  "result_mask_sha256": "...",
  "operation": "replace_mask",
  "confidence": 0.93
}
```

К payload прикладывается одна grayscale PNG или white-RGB/alpha carrier PNG. Для коррекций — небольшие cropped raster patches с `bbox` и операцией `restore/remove/set`, но самый надёжный первый вариант — replace whole mask: он проще для idempotency и проверки.

### 2. Держать один Photopea session на job/revision loop

```text
source ArrayBuffer
  → один Photopea document
  → duplicate SOURCE BACKUP into RESTORED / WITH GAPS
  → import one mask carrier
  → transparency selection via charID
  → add linked raster masks via charID
  → checkpoint renders
  → vision accept or raster correction
  → bounded repeat (например, максимум 3 revisions)
  → final PNG + PSD from the same document
```

Не нужно семь полноразмерных PNG-документов. Нужны source один раз, initial mask один раз и затем только correction patches либо одна replacement mask на revision.

### 3. Маску создавать в Photopea, но не пытаться «угадать» её полигонами

Практический алгоритм:

1. Передать source и mask carrier через Live Messaging `ArrayBuffer`.
2. Скопировать carrier layer в основной document как временный `MASK CARRIER`.
3. Сделать selection из transparency `Trsp → fsel` canonical charID sequence.
4. Активировать `RESTORED`, выполнить `Mk / Chnl / Msk / UsrM / RvlS`.
5. Повторить для `WITH GAPS` с нужной revision mask.
6. Сохранить grayscale pixels как `WORKING MASK`; удалить либо скрыть carrier.
7. Проверить выбор mask channel через `slct / Chnl / Msk`, но считать это только structural check.

Маска при этом является настоящей editable raster mask внутри Photopea. Внешний AI лишь доставляет pixel-level решение — ровно так же, как он доставлял бы brush strokes; это не «формальный PSD-контейнер» и не UI automation.

### 4. Реализовать настоящий checkpoint loop

Photopea после каждой revision должен экспортировать через `saveToOE("png")`:

- transparent artwork;
- grayscale mask preview;
- black, navy и blue-jean composites;
- при необходимости edge-band crop sheet.

Vision adapter получает эти exact bytes и возвращает `accept` либо typed raster correction. Каждая коррекция обязана ссылаться на `source_sha256`, `checkpoint_sha256` и parent revision. Любое несовпадение — 409 / stale revision, не silent reuse.

### 5. Сделать Photopea единственным финальным renderer

После `accept`:

1. экспортировать final transparent PNG из текущего document;
2. сохранить PSD;
3. закрыть/очистить session только после получения обоих артефактов;
4. записать их hashes в один `ArtifactRevision`.

Python-generated candidates остаются proposal/previews. Они не публикуются как authoritative final одновременно с другим Photopea mask.

### 6. Настоящий round-trip proof

Открыть **ровно возвращённый PSD** в чистом Photopea document и снова экспортировать:

- artwork PNG;
- linked mask pixels;
- black/navy/blue-jean renders.

Затем сравнить с pre-save accepted checkpoint:

- dimensions и layer types;
- non-empty bounds;
- exact mask hash либо заранее объявленный tolerance;
- RGB/alpha diff для protected regions = 0;
- final PNG equivalence;
- preview halo/vision result.

Только после этого ставить `X-Photopea-Roundtrip: verified` и terminal `passed`. Header должен быть следствием evidence object, а не самостоятельным доказательством.

### 7. Разделить runtimes JavaScript осознанно

Внутренний script Photopea разумно держать в ES5/Adobe-compatible стиле (`var`, обычные functions): Photopea официально эмулирует Photoshop scripting interface, и современный синтаксис там не даёт продуктовой пользы. Outer bridge — обычный Node.js и может использовать современный JS. Проблема не в «древнем JS», а в неподдерживаемом DOM/ActionDescriptor и неверном polygon representation.

## Предлагаемый порядок правок

1. Вернуть task 5.2 в incomplete и убрать ложный `verified` header до реального proof.
2. Ввести `RasterMaskRevision` + hash bindings; polygons оставить optional ROI.
3. Переделать transport без `Array.from()` и сделать один долгоживущий session на job.
4. Реализовать mask carrier → transparency selection → linked raster mask через charIDs.
5. Экспортировать final PNG и PSD из одной принятой Photopea revision.
6. Добавить checkpoint/correction endpoint и bounded vision loop.
7. Добавить реальный integration fixture: Live Photopea, save, reopen, pixel compare, full-size budget.
8. Сделать ожидание PSD default для этого Skill.
9. Восстановить полный PRD и связать требования → tests → exact artifacts/hashes.

## Что уже сделано хорошо

- Fail-closed вместо выдачи заведомо ложного PSD — правильное решение.
- Protected RGB/alpha diff и unauthorized alpha removal — хорошие машинно проверяемые инварианты.
- External-perimeter-only и intact-reference precedence существенно безопаснее глобального color key.
- Multipart `protected_reference`, path containment, idempotency и явные stage statuses двигают систему в правильную сторону.
- Текущие 46 тестов дают хорошую основу для pure core; их просто нельзя считать доказательством Photopea conformance.

## Acceptance criteria для следующей версии

Версию можно считать закрывающей проблему, когда один реальный API test на production-size fixture доказывает одновременно:

- source передан один раз, arbitrary scripts от клиента не принимаются;
- AI correction применяется как raster revision в том же Photopea document;
- есть минимум один checkpoint → review → correction/accept cycle;
- final PNG экспортирован из exact PSD revision;
- reopened PSD содержит непустые source/art/mask pixels и linked raster masks;
- mask и preview pixels совпадают с accepted checkpoint;
- protected RGB/alpha diff равен нулю;
- black/navy/blue-jean validation прошла;
- job не становится `passed` и Skill не завершает работу раньше этого proof.
