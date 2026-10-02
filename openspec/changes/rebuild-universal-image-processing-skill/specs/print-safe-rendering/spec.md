# Spec Delta

## Purpose

Гарантирует, что alpha-варианты и previews предназначены для печати на светлой и тёмной ткани, а не только для визуального просмотра на checkerboard.

## ADDED Requirements

### Requirement: Alpha-only rendering
Система MUST сохранять исходные visible RGB-пиксели и менять RGB только под полностью прозрачными пикселями при canonicalization.

#### Scenario: Alpha cleanup
- **WHEN** внешний фон удаляется
- **THEN** visible RGB совпадает с source, а hidden RGB может быть очищен до канонического значения

### Requirement: Premultiplied resize
Система MUST выполнять resize RGBA через premultiplied alpha.

#### Scenario: Transparent border resize
- **WHEN** artwork масштабируется
- **THEN** вокруг непрозрачных пикселей не появляется синтетический цветной fringe

### Requirement: Dark garment strategy
Система MUST проверять partial alpha через dark-garment/underbase preview и использовать binary или halftone fallback при обнаружении glow.

#### Scenario: Soft alpha creates glow
- **WHEN** preview на navy или Blue Jean показывает светлую кайму
- **THEN** continuous soft candidate не получает `passed`, а создаётся binary/halftone candidate или review request

### Requirement: Deterministic variants
Одинаковые source, policy и pipeline version MUST производить одинаковые variant pixels.

#### Scenario: Repeated processing
- **WHEN** один job повторно обрабатывается без изменения входов
- **THEN** hashes итоговых variants совпадают
