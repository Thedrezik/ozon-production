# Task 007 — Automatic Manager Tasks

status: pending  
complexity: HIGH  
recommended_model: GPT-5.6 Sol  
reasoning: High

## Goal

Создать систему задач руководителя.

Любая значимая производственная проблема должна автоматически становиться управляемой задачей, а не теряться в комментариях.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Создать сущность ManagerTask.
- Поля: source_type, source_id, order_id, title, description, severity, status, assigned_to, due_at, created_at, resolved_at.
- Статусы: OPEN, IN_PROGRESS, RESOLVED, DISMISSED.
- При создании production blocker автоматически создавать ManagerTask.
- Не создавать дубликаты одинаковой активной задачи для одной причины.
- Автоматически закрывать ManagerTask после устранения исходной причины там, где это безопасно.
- Подготовить rule engine для автоматических manager tasks.
- Поддержать источники: BLOCKER, DEADLINE_RISK, STALLED_ORDER, UNASSIGNED_ORDER, PROCUREMENT_OVERDUE, OZON_CANCELLED_AFTER_START, OZON_SYNC_ERROR, API_KEY_EXPIRING.
- Сделать экран 'Задачи руководителя'.
- Добавить фильтры: severity, source type, assignee, status.

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

- [ ] Создание blocker автоматически создаёт одну ManagerTask.
- [ ] Повторная обработка события не создаёт duplicate.
- [ ] Руководитель получает задачу в своём списке.
- [ ] Задачу можно взять в работу.
- [ ] Решение blocker корректно закрывает связанную задачу.
- [ ] Есть tests на deduplication.
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
