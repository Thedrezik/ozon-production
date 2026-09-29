# Task 017 — Notification Engine

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Создать единый движок уведомлений, независимый от конкретного канала доставки.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Создать Notification и NotificationPreference.
- Типы: NEW_ORDER, ORDER_CANCELLED, TARIFF_DEADLINE, SHIPMENT_DEADLINE, ORDER_OVERDUE, BLOCKER_CREATED, BLOCKER_RESOLVED, PROCUREMENT_CREATED, READY_TO_SHIP, OZON_SYNC_ERROR, API_KEY_EXPIRING.
- Каналы: IN_APP, WEB_PUSH, TELEGRAM.
- Поддержать обязательные admin notifications и пользовательские preferences.
- Дедуплицировать одинаковые автоматические уведомления.
- Не отправлять повторно событие при повторной webhook/reconciliation обработке.
- Сделать in-app notification center.

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

- [ ] Notification создаётся один раз на событие.
- [ ] Preferences учитываются.
- [ ] Manager получает blocker notification.
- [ ] In-app notifications отображаются.
- [ ] Tests на deduplication проходят.
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
