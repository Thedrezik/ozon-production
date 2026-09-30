# PROJECT STATE

Last updated: 2026-09-30

## Completed

- Task 001: application bootstrap, database, PWA and local Compose checks.
- Task 002: users, roles, permissions, sessions, admin bootstrap, audit log, login limiter, and frontend login/user management.
- Task 003: repeatable mock orders, production queue, assignments, internal status history, mobile task screens and SSE refresh.
- Task 004: full production transitions, configurable status labels/order, stage timestamps and cycle-time data.

## Current

- Task 004 complete. Apply migration `0004_production_workflow` before starting the updated API.

## Next

- Task 005 (see task file).

## Known Issues

- Docker is unavailable in this environment, so task 004 was not checked against the live PostgreSQL/Compose stack. SQLite migration and model comparison passed.
- The Problem button is a placeholder until the blockers task.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 15 pytest tests passed; Ruff passed; SQLite Alembic upgrade and `alembic check` passed.
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
