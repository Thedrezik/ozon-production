# Task 035 — Final Production Readiness Review

status: completed
complexity: HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Review boundary — 2026-10-02

Completed as **pre-deployment final review** by explicit user instruction before
renting VPS. Findings, PRODUCT/code coverage, simplification tradeoffs and fixed
regressions: [FINAL_REVIEW.md](../docs/FINAL_REVIEW.md). Task 034 stays `pending`;
its real Linux/Docker/HTTPS/PostgreSQL/restore/provider/physical-mobile acceptance
is deferred until final product corrections. No deployment, commit/push or task 036.
Completion here does not mean full PRODUCT compliance or production acceptance.

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

- [x] Все доступные critical tests проходят: backend 279, E2E 12/12, Ruff/frontend checks.
- [x] Подтверждённые в review дефекты исправлены с regressions; оставшиеся product gaps/launch blockers явно перечислены. Это не утверждение об отсутствии всех возможных production bugs.
- [x] Основной production scenario проходит от нового заказа до READY_TO_SHIP в реальном приложении с изолированными mock данными.
- [x] Blocker создаёт задачу руководителя и in-app уведомление; source resolution проверен.
- [x] Money at Risk объясним и прослеживается до конкретных заказов на подтверждённых mock costs; real tariff adapter остаётся blocker.
- [ ] Реальный Linux backup/restore проверен — deferred task 034; scripts/synthetic checks reviewed, live NOT RUN.
- [x] Deployment documented; runtime acceptance остаётся task 034.
- [x] STATE.md явно перечисляет оставшиеся blockers и границы review.

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
