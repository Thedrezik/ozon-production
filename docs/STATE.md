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
- Task 009: product production profiles by offer_id/SKU, admin CRUD, audit, and order normative-time display.
- Task 010: explainable production priority, confirmed tariff and value inputs, feasibility, blocked flag, audited manual override/pin, configurable weights, and ranked queue.
- Task 011: normalized tariff timeline, current/next step and signed Decimal financial effect, mock scenario, queue display and finance permission filtering.
- Task 012: Money at Risk totals by configurable local-time buckets, category split, finance-only paginated order drill-down, and conservative handling of unknown tariff costs.

## Current

- Task 012 complete. Apply migration `0011_tariff_engine` before starting the updated API; task 012 adds no migration.

## Next

- Next task has not started.

## Known Issues

- Docker is unavailable in this environment, so task 012 could not be checked against PostgreSQL/Compose.
- Browser mock smoke reached the new navigation but the in-app browser did not retain the local test session cookie, so the dashboard could not be visually verified after login. Its mock API drill-down passed through TestClient.
- Real Ozon tariff mapping remains pending official field/semantics verification during integration. No money at risk is inferred from order value or rates alone.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.
- Rules for sources beyond blockers and overdue procurement have a deduplicating rule boundary but await their source data and integrations.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 43 pytest tests passed; Ruff passed (SQLite test database).
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
- UI: local mock build opened; authenticated screen review was limited by in-app browser cookie handling.
