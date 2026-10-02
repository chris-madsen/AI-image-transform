# Spec Delta

## Purpose

Фиксирует пользовательское намерение в нормализованной policy и задаёт защищённые области, которые нельзя потерять при автоматической обработке.

## ADDED Requirements

### Requirement: Frozen processing policy
Система MUST нормализовать policy в фиксированные списки must_keep, keep_if_intentional, remove_only, garments, variants и edge strategy.

#### Scenario: Policy is normalized
- **WHEN** поля policy представлены допустимыми строками и enum values
- **THEN** downstream pipeline получает immutable normalized policy без повторного разбора текста

### Requirement: Protected details
Система MUST учитывать protected regions и не считать внутренние светлые детали фоном только из-за цвета.

#### Scenario: Protected rectangle overlaps background candidate
- **WHEN** protected region пересекается с candidate background mask
- **THEN** итоговая mask сохраняет эту область как artwork

### Requirement: No redraw
Система MUST изменять только alpha/mask и служебные artifacts, если пользователь явно не запросил цветовую операцию.

#### Scenario: Semantic model proposes regeneration
- **WHEN** внешний AI возвращает предложение перерисовать лицо или текст
- **THEN** предложение отклоняется и исходные RGB-пиксели остаются источником истины
