# PROJECT STATE

Last updated: 2026-09-30

## Completed

- Task 001: application bootstrap, database, PWA and local Compose checks.
- Task 002: users, roles, permissions, sessions, admin bootstrap, audit log, login limiter, and frontend login/user management.
- Task 003: repeatable mock orders, production queue, assignments, internal status history, mobile task screens and SSE refresh.
- Task 004: full production transitions, configurable status labels/order, stage timestamps and cycle-time data.
- Task 005: comments with author/time, mentions-ready links, and unified order timeline for comments, statuses and assignments.
- Task 006: production blockers, manager tasks, status restoration, timeline/audit and mobile problem actions.
- Task 007: manager task queue, source-keyed deduplication and resolution boundary, manager permissions, filters and claim flow.
- Task 008: procurement tasks, links to multiple orders and blockers, purchaser queue, history, overdue escalation through manager tasks, and mobile procurement screen.

## Current

- Task 008 complete. Apply migration `0008_procurement` before starting the updated API.

## Next

- Next task is not started.

## Known Issues

- Docker is unavailable in this environment, so task 008 could not be checked against PostgreSQL/Compose. SQLite migration and model comparison passed.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.
- Rules for sources beyond blockers and overdue procurement have a deduplicating rule boundary but await their source data and integrations.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 21 pytest tests passed; Ruff passed; SQLite Alembic upgrade and `alembic check` passed.
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
