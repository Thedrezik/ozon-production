# Task 015 — Search, Filters and Bulk Actions

status: pending  
complexity: LOW  
recommended_model: GPT-5.6 Luna / Instant  
reasoning: Low

## Goal

Добавить удобный поиск, фильтры и безопасные массовые действия.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Поиск по posting number, order number, SKU, offer_id, product name.
- Фильтры: internal status, Ozon status, priority, worker, blocked, ready, overdue, warehouse, product.
- Pagination обязательна.
- Manager/admin может выбирать несколько заказов.
- Bulk actions: assign, send to production, change compatible status.
- Опасные действия требуют подтверждения.
- Каждый bulk action проверяет permission backend.
- Bulk изменения фиксируются в audit.

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

- [ ] Поиск работает.
- [ ] Комбинация фильтров работает.
- [ ] Pagination работает.
- [ ] Bulk assignment работает.
- [ ] Недопустимый bulk status transition отклоняется.
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
