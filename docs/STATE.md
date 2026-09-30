# PROJECT STATE

Last updated: 2026-09-30

## Completed

- Task 001: application bootstrap, database, PWA and local Compose checks.
- Task 002: users, roles, permissions, sessions, admin bootstrap, audit log, login limiter, and frontend login/user management.
- Task 003: repeatable mock orders, production queue, assignments, internal status history, mobile task screens and SSE refresh.
- Task 004: full production transitions, configurable status labels/order, stage timestamps and cycle-time data.
- Task 005: comments with author/time, mentions-ready links, and unified order timeline for comments, statuses and assignments.
- Task 006: production blockers, manager tasks, status restoration, timeline/audit and mobile problem actions.

## Current

- Task 006 complete. Apply migration `0006_blockers` before starting the updated API.

## Next

- Next task is not started.

## Known Issues

- Docker is unavailable in this environment, so task 006 was not checked against PostgreSQL/Compose. SQLite migration and model comparison passed.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 17 pytest tests passed; Ruff passed; SQLite Alembic upgrade and `alembic check` passed.
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
