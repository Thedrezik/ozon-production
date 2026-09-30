# PROJECT STATE

Last updated: 2026-09-30

## Completed

- Task 001: application bootstrap, database, PWA and local Compose checks.
- Task 002: users, roles, permissions, sessions, admin bootstrap, audit log, login limiter, and frontend login/user management.
- Task 003: repeatable mock orders, production queue, assignments, internal status history, mobile task screens and SSE refresh.

## Current

- Task 003 complete. Apply migration `0003_mock_orders` and run `python -m app.cli seed-mock-orders` in Mock Mode to populate the queue.

## Next

- Task 004: production workflow.

## Known Issues

- Docker is unavailable in this environment, so task 003 was not checked against the live PostgreSQL/Compose stack. SQLite migration and model comparison passed.
- The Problem button is a placeholder until the blockers task.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 15 pytest tests passed; Ruff passed; SQLite Alembic upgrade and `alembic check` passed.
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
