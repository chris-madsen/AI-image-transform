# Spec Delta

## Purpose

Определяет проверяемое описание исходного artwork до изменения маски, чтобы последующие операции опирались на фактические RGBA-данные и могли безопасно остановиться.

## ADDED Requirements

### Requirement: Source freeze
Система MUST сохранить исходный байтовый файл и его sha256 до начала обработки.

#### Scenario: Source is preserved
- **WHEN** job принят
- **THEN** исходный файл доступен по immutable source reference и его hash записан в report

### Requirement: RGBA inspection
Система MUST определить geometry, mode, наличие alpha, alpha histogram и hidden RGB statistics.

#### Scenario: Opaque input is inspected
- **WHEN** загружен JPEG или непрозрачный PNG
- **THEN** report явно указывает отсутствие исходной прозрачности и не притворяется, что alpha была предоставлена

### Requirement: Edge classification
Система MUST классифицировать внешний edge-connected фон отдельно от внутренних пикселей и указывать crop risk.

#### Scenario: Flat external background
- **WHEN** одинаковый фон связан с границами canvas
- **THEN** inspection помечает его как removable external background и считает его connected area

#### Scenario: Artwork touches canvas boundary
- **WHEN** значимая область касается границы и фон нельзя надёжно отличить
- **THEN** inspection выставляет crop risk и требует review вместо безусловного удаления
