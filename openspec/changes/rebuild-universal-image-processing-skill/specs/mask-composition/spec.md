# Spec Delta

## Purpose

Определяет построение маски из edge connectivity, source alpha, semantic protection и локальных исправлений без глобального опасного threshold.

## ADDED Requirements

### Requirement: Connected external background
Система MUST удалять только фон, связанный с краями canvas, если policy не содержит явного локального разрешения.

#### Scenario: Similar internal color
- **WHEN** такой же цвет встречается внутри объекта, но не связан с краем
- **THEN** внутренний участок остаётся непрозрачным

### Requirement: Mask revision
Каждое изменение маски MUST создаваться как новая revision и не изменять предыдущую mask.

#### Scenario: Manual correction
- **WHEN** reviewer добавляет или вычитает область
- **THEN** создаётся новая revision с parent reference и audit metadata

### Requirement: Uncertainty handling
Система MUST сохранять uncertainty/review regions и не выдавать ambiguous candidate как безусловно passed.

#### Scenario: Low-confidence segmentation
- **WHEN** segmentation confidence ниже policy threshold
- **THEN** candidate получает `review_required` или `refused`
