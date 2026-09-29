# Task 004 — Production Workflow

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Реализовать полноценный внутренний workflow мебельного производства.

Ozon status и внутренний production status должны оставаться независимыми сущностями.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Реализовать configurable internal statuses.
- Минимальные статусы: NEW, QUEUED, SENT_TO_PRODUCTION, IN_PRODUCTION, BLOCKED, PRODUCED, QUALITY_CHECK, PACKING, READY_TO_SHIP, HANDED_TO_SHIPPING, DONE, CANCELLED.
- Реализовать допустимые переходы между статусами.
- Запрещать некорректные переходы на backend.
- Хранить status history: old_status, new_status, user, timestamp.
- Добавить возможность администратору менять отображаемые названия и порядок статусов без изменения системных кодов.
- Добавить timestamps начала и окончания ключевых производственных этапов.
- Подготовить данные для последующего расчёта cycle time.

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

- [ ] Корректные переходы работают.
- [ ] Некорректные переходы отклоняются backend.
- [ ] История статусов сохраняется.
- [ ] Несколько пользователей видят актуальный статус.
- [ ] Ozon status не изменяется при изменении production status.
- [ ] Tests проходят.
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
