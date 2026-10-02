# Spec Delta

## Purpose

Выносит решение о качестве в явную validation-модель с измеримыми проверками halo, frame, protected details, bounds и разрешением на безопасный отказ.

## ADDED Requirements

### Requirement: Validation decision
Каждый candidate MUST завершаться ровно одним решением `passed`, `review_required`, `refused` или `failed`.

#### Scenario: Safe candidate
- **WHEN** все обязательные checks пройдены и crop risk отсутствует
- **THEN** candidate получает `passed`

#### Scenario: Unsafe candidate
- **WHEN** потеряна protected detail или обнаружен halo/frame
- **THEN** candidate не получает `passed` и содержит warning/review region

### Requirement: Required previews
Система MUST создавать previews на black, white, gray, navy, Blue Jean и DTG-underbase, а также alpha-mask preview.

#### Scenario: Preview set is complete
- **WHEN** validation запускается для candidate
- **THEN** report содержит artifact reference каждого обязательного preview

### Requirement: Batch isolation
Система MUST валидировать batch items независимо и сохранять успешные результаты при ошибке другого item.

#### Scenario: One item fails
- **WHEN** один source не проходит inspection
- **THEN** остальные jobs получают собственные результаты и не становятся failed из-за соседнего item
