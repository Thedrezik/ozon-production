# Task 024 — Ozon Cancellations and Changes

status: pending  
complexity: MEDIUM/HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Корректно обрабатывать отмены и существенные изменения Ozon после начала производственного процесса.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- При отмене Ozon не удалять локальный order.
- Убирать cancelled order из обычной очереди.
- Если производство уже начато — автоматически создавать ManagerTask.
- Отправлять уведомление ответственному и manager.
- Обрабатывать изменение shipment date.
- Пересчитывать priority и Money at Risk после существенных изменений.
- Фиксировать старые и новые значения в audit/timeline.

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

- [ ] Cancelled-before-production корректно закрывается.
- [ ] Cancelled-after-production-start создаёт задачу руководителя.
- [ ] Изменение deadline вызывает recalculation.
- [ ] История сохраняется.
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
