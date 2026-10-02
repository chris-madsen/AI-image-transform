# Spec Delta

## Purpose

Определяет обязательный для PSD export мост между image service и Photopea outer environment через официальный Live Messaging API.

## ADDED Requirements

### Requirement: Bridge boundary
Photopea Live API adapter MUST быть отдельным adapter; он не должен содержать domain mask logic, но MUST быть вызван до `passed` результата с PSD.

#### Scenario: Bridge unavailable
- **WHEN** Photopea или browser outer environment недоступны
- **THEN** основной job может сохранить диагностические PNG/mask artifacts, но получает `review_required` или `failed`, а не `passed`

### Requirement: PSD/PNG exchange
Bridge MUST передавать выбранные PNG/mask artifacts и Photopea script, а возвращённые PSD/PNG сохранять с job correlation.

#### Scenario: Export through outer environment
- **WHEN** пользователь запускает Photopea export
- **THEN** returned file связывается с исходным job и проходит обычную artifact validation

### Requirement: No UI automation dependency
Bridge MUST использовать документированный message/script boundary, а не зависеть от координат мыши или расположения кнопок.

#### Scenario: Photopea UI changes
- **WHEN** меняется layout интерфейса Photopea
- **THEN** contract-level bridge остаётся работоспособным, если API message boundary не изменился

### Requirement: Layer construction
Bridge MUST создать в Photopea source backup, working art, working mask и named test-background layers перед экспортом PSD.

#### Scenario: PSD structure is exported
- **WHEN** Photopea получает candidate artifacts
- **THEN** returned PSD содержит требуемые независимые layers и исходный canvas size
