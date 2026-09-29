# Task 029 — Audit Log

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Завершить полноценный immutable audit trail ключевых действий.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Audit поля: user, action, entity_type, entity_id, old_value, new_value, timestamp, IP/user-agent где уместно.
- Логировать status changes, assignments, priority override, blockers, procurement, roles, settings, integration changes.
- Не логировать passwords, session tokens и API keys.
- Обычные пользователи не могут редактировать audit.
- Admin/viewer с audit.view может просматривать и фильтровать.
- Не использовать audit table как business event store.

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

- [ ] Все критические действия имеют audit record.
- [ ] Sensitive secrets отсутствуют.
- [ ] Фильтрация audit работает.
- [ ] Audit нельзя редактировать через обычный API.
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
