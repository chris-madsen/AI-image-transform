# Spec Delta

## Purpose

Формирует полный, проверяемый и редактируемый набор результатов для скачивания, ручной проверки и последующей работы в Photopea.

## ADDED Requirements

### Requirement: Artifact bundle
Система MUST выдавать PNG, mask, alpha-mask, required previews, JSON report и editable PSD для завершённого job.

#### Scenario: Passed bundle
- **WHEN** candidate получил `passed`
- **THEN** artifact list содержит имена, media types, byte sizes и sha256 всех обязательных файлов

### Requirement: Layered PSD
PSD MUST создаваться через Photopea Live API и содержать source backup, working art, working mask и named test-background layers без потери размера canvas.

#### Scenario: PSD is opened in editor
- **WHEN** пользователь открывает PSD в совместимом редакторе
- **THEN** source, mask и test-background layers доступны отдельно для ручной коррекции

### Requirement: PSD export dependency
Job MUST NOT получить `passed` с отсутствующим или локально сгенерированным PSD; отсутствие Photopea Live API adapter приводит к `review_required` или `failed`.

#### Scenario: Photopea Live API adapter unavailable
- **WHEN** PNG и mask готовы, но Photopea Live bridge недоступен
- **THEN** job не получает `passed` и report содержит явную bridge error

### Requirement: Report provenance
JSON report MUST содержать source hash, policy, pipeline version, validation decision, changed-pixel statistics, warnings и artifact manifest.

#### Scenario: Audit report
- **WHEN** пользователь получает bundle
- **THEN** report позволяет связать каждый artifact с source и конкретной processing revision
