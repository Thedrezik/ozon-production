# Task 022 — Ozon Webhook

status: pending  
complexity: HIGH  
recommended_model: GPT-5.6 Sol  
reasoning: High

## Goal

Подключить актуальные push/webhook события Ozon для максимально быстрого появления изменений.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Перед реализацией проверить официальную документацию webhook/push.
- Не придумывать signature verification, если документация её не требует.
- Реализовать endpoint согласно требованиям Ozon.
- Поддержать verification/handshake, если он требуется.
- Хранить ozon_webhook_events.
- Использовать idempotency.
- Повторное событие не должно менять данные дважды и создавать duplicate notifications/tasks.
- Обработка должна быстро возвращать подходящий HTTP status.
- Тяжёлую дополнительную обработку не выполнять до ответа, если это нарушает требования webhook.

## General Constraints

- Не менять несвязанные части системы без необходимости.
- Не делать большой refactoring одновременно с реализацией задачи.
- Не добавлять тяжёлую инфраструктуру без доказанной необходимости.
- Учитывать VPS примерно 1 CPU / 1 GB RAM.
- Проверять permissions на backend.
- Все timestamps хранить в UTC.
- Денежные значения считать через Decimal/NUMERIC, не float.
- Не коммитить secrets.
- Не выводить secrets в logs.
- Важные изменения фиксировать в audit, если audit infrastructure уже существует.
- Если принимается новое существенное архитектурное решение — кратко записать его в `/docs/DECISIONS.md`.

## Acceptance Criteria

- [ ] Webhook endpoint проходит требования Ozon.
- [ ] New posting event обрабатывается.
- [ ] Duplicate event безопасен.
- [ ] Cancellation/status changes обрабатываются.
- [ ] Webhook event сохраняется для диагностики.
- [ ] Tests idempotency проходят.
- [ ] STATE.md обновлён.

## Completion

Перед завершением задачи:

1. Проверить все acceptance criteria.
2. Запустить связанные backend tests.
3. Запустить frontend tests/lint/typecheck, если задача затрагивает frontend.
4. Исправить обнаруженные ошибки.
5. Обновить `/docs/STATE.md`.
6. Изменить `status: pending` этого task на `status: completed`, если задача полностью закончена.

Финальный отчёт должен быть коротким:

- что реализовано;
- основные изменённые файлы;
- какие tests запущены;
- результат tests;
- оставшиеся проблемы, если есть.

Не печатать содержимое целых исходных файлов в финальном ответе.
