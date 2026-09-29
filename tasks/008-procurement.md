# Task 008 — Procurement Tasks

status: pending  
complexity: MEDIUM  
recommended_model: GPT-5.6 Sol  
reasoning: Medium

## Goal

Создать лёгкую систему закупочных задач для материалов и комплектующих.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Создать ProcurementTask.
- Статусы: NEW, ORDERED, PURCHASED, DELIVERED, CANCELLED.
- Поля: material_name, quantity, unit, description, responsible_user, needed_by, timestamps.
- Одна procurement task может быть связана с несколькими заказами и blockers.
- Из blocker должна быть кнопка 'Создать закупку'.
- После доставки материала связанные blockers не закрывать молча без подтверждения, если это может быть неоднозначно.
- Сделать экран закупок.
- Добавить overdue indication.
- Просроченная важная закупка может создавать ManagerTask.

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

- [ ] Из blocker создаётся procurement task.
- [ ] Закупка может быть связана с несколькими заказами.
- [ ] Ответственный видит свои закупки.
- [ ] Просрочка определяется корректно.
- [ ] История изменений сохраняется.
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
