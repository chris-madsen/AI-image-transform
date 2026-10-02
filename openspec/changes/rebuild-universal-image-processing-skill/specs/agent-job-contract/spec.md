# Spec Delta

## Purpose

Предоставляет Skill стабильный асинхронный контракт для запуска, наблюдения и получения результатов обработки изображений без зависимости от пользовательского интерфейса.

## ADDED Requirements

### Requirement: Job creation
Сервис MUST принимать один artwork, manifest и frozen ProcessingPolicy и возвращать уникальный job identifier со статусом `accepted`.

#### Scenario: Valid job is accepted
- **WHEN** клиент отправляет поддерживаемый файл и валидную policy
- **THEN** сервис возвращает `202`, `job_id` и `poll_url` со статусом `accepted`

#### Scenario: Invalid policy is rejected
- **WHEN** policy содержит неизвестный enum или некорректные protected regions
- **THEN** сервис возвращает структурированную ошибку валидации и не создаёт исполняемый job

### Requirement: Job status
Сервис MUST предоставлять текущий статус job и итоговый validation decision.

#### Scenario: Client polls a running job
- **WHEN** клиент запрашивает существующий job
- **THEN** ответ содержит status, timestamps, progress и warnings без исходных секретов

#### Scenario: Unknown job
- **WHEN** клиент запрашивает неизвестный job identifier
- **THEN** сервис возвращает `404` с машиночитаемым кодом ошибки

### Requirement: Artifact discovery
Сервис MUST публиковать только immutable artifacts завершённого job.

#### Scenario: Completed artifacts are listed
- **WHEN** job имеет статус `passed`, `review_required` или `refused`
- **THEN** список содержит name, media type, size и sha256 каждого доступного artifact

#### Scenario: Failed job has no false success
- **WHEN** обработка завершилась с ошибкой
- **THEN** статус остаётся `failed`, а отсутствующий artifact не объявляется готовым

### Requirement: Idempotent submission
Сервис MUST поддерживать повторную отправку с одинаковым idempotency key без создания второго job.

#### Scenario: Retry after network timeout
- **WHEN** клиент повторяет запрос с тем же idempotency key и тем же source hash
- **THEN** сервис возвращает исходный job identifier
