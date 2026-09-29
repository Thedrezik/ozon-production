# Task 035 — Final Production Readiness Review

status: pending  
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Провести финальный review проекта перед использованием в реальном производстве.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Не добавлять новые крупные функции без критической необходимости.
- Проверить PRODUCT.md против фактически реализованного MVP.
- Проверить database migrations.
- Проверить tests.
- Проверить Ozon integration.
- Проверить webhook/reconciliation idempotency.
- Проверить Money at Risk.
- Проверить Manager Tasks и blocker flow.
- Проверить RBAC/security.
- Проверить backup/restore.
- Проверить production deployment.
- Проверить mobile worker workflow.
- Исправить blocking issues.
- Составить короткий список non-blocking future improvements.

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

- [ ] Все critical tests проходят.
- [ ] Нет известных blocking bugs.
- [ ] Основной production scenario проходит от нового заказа до READY_TO_SHIP.
- [ ] Blocker создаёт задачу руководителя и уведомление.
- [ ] Money at Risk объясним и прослеживается до конкретных заказов.
- [ ] Backup/restore проверен.
- [ ] Deployment documented.
- [ ] STATE.md отражает production-ready состояние либо явно перечисляет оставшиеся blockers.

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
