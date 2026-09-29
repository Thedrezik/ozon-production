# Task 006 — Production Blockers

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Реализовать полноценную систему проблем производства.

Проблема не должна быть просто текстовым комментарием.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Создать Blocker и BlockerType.
- Типы по умолчанию: MATERIAL_MISSING, EDGE_TAPE_MISSING, HARDWARE_MISSING, PACKAGING_MISSING, PART_MISSING, DEFECT, REWORK, EQUIPMENT_FAILURE, PICKING_ERROR, CLARIFICATION, OTHER.
- Статусы blocker: OPEN, IN_PROGRESS, RESOLVED, CANCELLED.
- Поля: order/posting, type, description, severity, creator, assigned_to, expected_resolution_at, timestamps.
- При создании blocker заказ при необходимости переводить в BLOCKED.
- Хранить предыдущий production status, чтобы после решения можно было корректно продолжить работу.
- Разрешить прикладывать фотографии, если file infrastructure уже существует; иначе подготовить интерфейс.
- Записывать события в timeline и audit.

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

- [ ] Worker может создать blocker.
- [ ] Manager видит blocker.
- [ ] Заказ корректно маркируется как blocked.
- [ ] Blocker можно взять в работу и решить.
- [ ] После решения заказ можно продолжить.
- [ ] История не теряется.
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
