# Review: AI-image-transform / Photopea mask pipeline

**Дата:** 2026-10-04; повторное ревью 2026-10-06
**Ревизия:** `5faef40` (`fix: complete Photopea raster-mask round trip`)
**Репозиторий:** <https://github.com/chris-madsen/AI-image-transform>
**Вердикт:** **STOP SHIP.** Технический raster-mask round trip в Photopea теперь
работает, но продуктовый workflow по-прежнему не реализован. Код принимает
готовую маску от вызывающей стороны, выдаёт её за Photopea-authored result,
не запускает специализированную matting-модель, не вызывает production review
loop и передаёт vision reviewer только хеши. Хорошо проверенная передача плохой
маски остаётся плохим результатом.

## Повторное ревью 2026-10-06: что сделано принципиально неправильно

### P0 — `photopea_mask` вообще не должен быть публичным входом

Предыдущая версия этого review была слишком мягкой: она допускала, что внешний
AI создаёт raster mask, а Photopea только переносит её в linked layer mask. Это
не исходный продуктовый замысел. Финальная editable mask должна создаваться в
Photopea; внешний raster допустим только как **внутренний неавторитетный model
proposal** или как correction после review конкретного Photopea checkpoint.

Фактическая реализация делает обратное:

- `POST /v1/jobs` принимает multipart-поле `photopea_mask`
  (`src/printify_artwork_cleaner/service.py:290-317`);
- `_decode_resolved_masks()` декодирует его отдельно и возвращает как
  `authoritative_mask` (`service.py:47-70`);
- `process_image_bytes()` безусловно заменяет им alpha и обе candidate masks
  (`application.py:77-93`);
- helper публично предлагает `--photopea-mask` и загружает файл в job
  (`skill/universal-image-matting/scripts/submit_artwork_job.py:50-61`);
- `PhotopeaLiveApiAdapter` затем только доказывает, что эти же входные пиксели
  пережили перенос в PSD.

Это обход всей системы, которую требовалось построить. Caller может передать
рваную маску с потерянными ушами, глазами, усами и листвой; hashes, PSD reopen
и pixel equivalence честно подтвердят, что Photopea сохранила именно эту рваную
маску. Никакой conformance proof не превращает неверный input в правильный art.

Обязательное исправление: удалить `photopea_mask` из public job schema, CLI и
Skill. Service должен сам запускать model proposal stage, открыть Photopea,
создать working raster mask внутри документа, показать checkpoint reviewer'у и
только после accept экспортировать final PNG + PSD.

### P0 — специализированного mask provider нет; LLM поставлена не на своё место

`VisionProvider` в `ports.py:24-37` — только `Protocol`. Реализации, загрузки
weights, provider configuration и вызова `resolve_masks()` в production нет.
В репозитории нет BiRefNet, BEN2, SAM 2.1 или matting/refinement provider. Это
не «будущий adapter», а отсутствующее ядро автоматической функции продукта.

LLM не должна генерировать alpha pixels. Её нормальная роль:

- понять пользовательское намерение;
- определить must-keep/remove-only semantics и режим;
- дать coarse semantic prompts/ROI;
- визуально сравнить exact checkpoint renders и принять/отклонить результат.

Пиксельные proposals должны делать специализированные модели:

1. **BiRefNet HR-matting** — primary high-resolution alpha proposal;
2. **BEN2** — независимый второй proposal/consensus candidate;
3. **SAM 2.1** — semantic protection и ROI, не финальная soft alpha;
4. **ViTMatte** — refinement по trimap в зоне disagreement.

Версии, лицензии и hashes weights обязаны попадать в evidence. Для коммерческого
Etsy/Printify workflow нельзя молча брать non-commercial weights. Model output
остаётся proposal; protected precedence, exterior-only scope и Photopea review
остаются обязательными.

### P0 — production vision review loop отсутствует

`run_bounded_photopea_review()` существует, но production `ServiceRuntime` его
не вызывает. Функция используется только в `tests/test_photopea_review.py`.
Реальный `_run_deferred_psd()` выбирает уже созданный PNG/mask и вызывает
one-shot `self.psd_exporter.export(...)` (`service.py:144-191`). Никаких
`PhotopeaSessionClient.open() → review → apply_revision() → finalize()` в job
orchestration нет.

Значит task 5.6 не просто «частично готова» — она отмечена `[x]` без реализации
главного production path. Unit test чистой функции не доказывает, что функция
встроена в продукт.

### P0 — reviewer физически нечего смотреть

`PhotopeaCheckpoint` и `PhotopeaSessionCheckpoint` содержат IDs и hashes, но не
artifact bytes/URLs. `bridge/server.mjs::checkpointSummary()` возвращает только
`revision_id`, `source_sha256`, `checkpoint_sha256`, `mask_sha256` и
`artwork_sha256` (`bridge/server.mjs:787-796`). Black/navy/blue-jean previews в
памяти bridge существуют, но наружу reviewer'у не выдаются.

Хеш — доказательство идентичности, не изображение. Vision model не может по
SHA-256 увидеть оторванное ухо, дырку над головой, исчезнувшие листья или грязный
нижний fade. Любой `accepted=true` при таком контракте будет либо заглушкой,
либо неподтверждённой декларацией.

Checkpoint обязан давать краткоживущие authenticated URLs или bytes для:

- transparent artwork;
- grayscale working mask;
- black preview;
- navy preview;
- Blue Jean preview;
- при необходимости edge-band/contact sheet.

И только эти exact artifacts вместе с hashes могут входить в vision decision.

### P0 — task/status governance нарушает собственный OpenSpec workflow

В репозитории действительно лежат OpenSpec/SDD skills в `.agents/skills/`,
сгенерированные OpenSpec 1.14.0. Нельзя доказать по git, запускал ли исполнитель
конкретную команду, но можно доказать, что обязательные guardrails не соблюдены.
`openspec-apply-change` требует:

- прочитать все `contextFiles`;
- при design issue остановиться и обновить artifacts;
- не сужать и не откладывать требование молча;
- ставить `[x]` только после полной реализации поведения.

Исполнитель вместо этого зафиксировал ошибочный public mask contract в PRD,
обоих changes, Skill и коде; оставил loop test-only; не дал reviewer'у images;
после этого отметил 5.2, 5.5 и 5.6 выполненными. Это ровно то, что workflow
запрещает. Поэтому ответ на вопрос «использовал ли он SDD prompts/skills» такой:
файлы skills присутствуют, но результат не соответствует их обязательному
процессу. В текущем окружении `openspec` CLI отсутствует, поэтому заявления о
strict validation независимо не воспроизводятся.

### P1 — evidence: отсутствие PSD в GitHub не является дефектом

Предыдущее замечание «evidence отсутствует в GitHub» уточняется. PSD не
закоммичен по прямому указанию product owner, и это нормально: тяжёлые бинарные
артефакты не обязаны жить в git. Дефект другой: evidence matrix ссылается на
`artifacts/photopea-full-smoke-20261006/`, которого в репозитории нет, без
пометки, что это local/non-versioned evidence, и без достаточного воспроизводимого
заменителя.

Правильная evidence запись без PSD binary должна содержать exact command,
source fixture SHA-256, commit SHA, Photopea/browser/model versions, weights
hashes, elapsed time, returned PNG/PSD hashes и verification log. Не требовать
коммитить PSD; не ссылаться на несуществующий repo path как на доступный artifact.

### P1 — «same document» и five-minute budget пока не доказаны продуктово

Bridge умеет держать session object, но `photopeaRevisionScript()` закрывает
старый output document и перестраивает revision из source + carrier. Это не то
же самое, что локально править working mask в уже проверенном документе. Кроме
того, заявленный full-size smoke занял 232.39 s при 300 s TTL: на настоящий цикл
из initial checkpoint, review, одной-двух revisions, finalize и reopen остаётся
слишком мало запаса. Тайм-бюджет надо измерять для полного job-level flow, а не
для прямого bridge smoke.

### P1 — текущие автоматические quality metrics не поймают эту пантеру

`fragmentation_score` в основном ловит отдельные/почти отдельные pixels. Большая
рваная дырка, срезанная листва или потерянный кусок головы могут быть связной
областью и пройти. Hash equivalence и zero protected diff помогают только если
правильная protection mask уже существует. На проблемной пантере именно этот
semantic/proposal слой отсутствует.

Нужен полноразмерный golden fixture с approved alpha/reference preview и
обязательными region checks: оба уха, глаза, усы, листва над головой, правый
контур, нижний soft fade и отсутствие новых внутренних holes. Screen-like
`soft_alpha` и `dark_dtg_safe` должны быть отдельными outputs: широкая
полупрозрачность, красиво выглядящая на Blue Jean preview, может дать светлую
DTG underbase/glow на ткани.

## Исправленная целевая архитектура

```text
source + intent-only policy
  -> BiRefNet HR proposal + BEN2 proposal
  -> SAM 2.1 protection / ROI
  -> consensus + uncertainty trimap
  -> optional ViTMatte refinement
  -> deterministic exterior-only/protected-pixel constraints
  -> one Photopea document authors editable working mask
  -> checkpoint bytes/URLs: artwork + mask + black/navy/Blue Jean
  -> concrete vision accept or typed internal raster correction
  -> bounded repeat in the same document
  -> final PNG + PSD from the accepted revision
  -> reopen + pixel/structure/preview proof
```

Распределение ответственности:

| Компонент | Что делает | Чего не делает |
|---|---|---|
| LLM/vision | Intent, semantic prompts, preview comparison, accept/reject | Не рисует alpha pixels |
| Specialized models | Proposal alpha, protection, trimap/refinement | Не объявляют proposal финальным PSD mask |
| Deterministic core | Exterior-only scope, precedence, hashes, invariants | Не выдумывает semantic pixels |
| Photopea | Авторит editable raster mask, checkpoints, final PNG/PSD | Не принимает client final mask как истину |

## Обязательные правки до следующей попытки acceptance

1. Удалить `photopea_mask` и `--photopea-mask` из public API/helper.
2. Убрать `photopea_mask_revision` и post-checkpoint `visual_quality` из initial
   caller policy; это runtime evidence.
3. Реализовать минимум один pinned specialized matting provider и независимый
   второй proposal path.
4. Передавать proposals в Photopea только внутренне и создавать editable working
   mask внутри Photopea.
5. Выдать reviewer'у exact checkpoint images, а не только hashes.
6. Встроить `run_bounded_photopea_review()`/session client в `ServiceRuntime`.
7. Запретить one-shot finalize без hash-bound accept decision.
8. Добавить full-resolution panther golden test и два print profiles:
   `soft_alpha` и `dark_dtg_safe`.
9. Вернуть tasks 5.2, 5.5, 5.6 и связанные 4.2/6.2/6.4 в unchecked.
10. Не коммитить PSD, если product owner запретил; вместо этого хранить
    воспроизводимый manifest/log/hashes и честно маркировать local evidence.

Ни одна из этих правок не является косметикой. Пока они не сделаны, система
автоматизирует упаковку чужой маски в корректный PSD, но не решает задачу
автоматического качественного matting и Photopea review.

---

Ниже сохранена историческая часть review от 2026-10-04. Её технические замечания
про старый polygon path относятся к предыдущей ревизии; новое повторное ревью
выше имеет приоритет там, где формулировки расходятся.

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
