# PROJECT STATE

Last updated: 2026-09-30

## Completed

- Task 001: application bootstrap, database, PWA and local Compose checks.
- Task 002: users, roles, permissions, sessions, admin bootstrap, audit log, login limiter, and frontend login/user management.

## Current

- Task 002 complete. Existing local Compose stack needs rebuild and migration before the new auth UI is available.

## Next

- Task 003 has not been started.

## Known Issues

- No live PostgreSQL/Compose validation for task 002 in this environment. SQLite migration and automated tests passed.

## Ozon Integration

- Not connected. Mock Mode remains enabled; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head`, then create the first admin with `python -m app.cli create-admin`.

## Last Tests

- Backend: 12 pytest tests passed; Ruff passed; SQLite Alembic upgrade reached `0002_auth_rbac` and seeded 7 roles.
- Frontend: ESLint and TypeScript passed; Vite PWA build passed using `--configLoader runner`.
