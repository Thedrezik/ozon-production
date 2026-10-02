# Task 033 — End-to-End Tests

status: completed
complexity: MEDIUM/HIGH  
recommended_model: GPT-6 Sol
reasoning: Medium

## Goal

Создать E2E coverage главного бизнес-сценария.

## Read First

Обязательно прочитать:

- `/AGENTS.md`
- `/docs/STATE.md`
- `/docs/ARCHITECTURE.md`, если файл уже существует
- `/docs/DECISIONS.md`, если файл уже существует

Читать `/docs/PRODUCT.md` только в относящихся к задаче разделах, если текущей задачи недостаточно.

Не загружать весь репозиторий в контекст без необходимости.

## Requirements

- Использовать mock Ozon/test environment.
- Сценарий: admin login.
- Создание/наличие worker.
- Появление заказа.
- Worker берёт заказ.
- Начинает производство.
- Создаёт blocker.
- Manager получает ManagerTask.
- Из blocker создаётся procurement task.
- Blocker решается.
- Производство продолжается.
- Заказ производится.
- Packing.
- READY_TO_SHIP.
- Проверить audit/timeline.
- Проверить минимум один Money at Risk сценарий.

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

- [x] Главный E2E сценарий проходит.
- [x] Тест детерминирован.
- [x] Не требует production Ozon.
- [x] Ошибка E2E оставляет понятный diagnostic output.
- [x] STATE.md обновлён.

Verification: `cd frontend && npm run test:e2e` — 12 passed, twice from fresh
databases; desktop 1440×1000 and mobile 390×844, zero retries. Backend 273 passed;
Ruff app/tests/Alembic, frontend lint/typecheck/build, offline snapshot checks and
git diff --check passed. Coverage/setup/deployment boundaries: `/docs/E2E.md`.
Docker unavailable: PostgreSQL/Caddy/container verification remains task 034.
No commit/push; task 034 not started.

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
