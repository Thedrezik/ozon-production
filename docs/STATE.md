# PROJECT STATE

Last updated: 2026-10-01

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
- Task 013: manager dashboard with risk, urgent order and task counts, attention list, staff workload, and filtered drill-downs.
- Task 014: worker-first mobile navigation for My Tasks, Queue and Problems; priority-ranked Next Task selection using existing queue/claim APIs; compact worker cards and permission-aware financial detail visibility.
- Task 015: queue search across posting/order numbers, SKU, offer_id and product; combined status/Ozon status/priority/worker/blocker/readiness/deadline/warehouse/product filters; safe paginated bulk assignment/status transitions with backend permissions and audit.
- Task 016: shared SSE refresh for orders, blockers and manager tasks across active screens; reconnect, focus and periodic API reconciliation.
- Task 017: transactional in-app notification center, per-user preferences, admin alerts, deduplication, deadline reconciliation, and pending Web Push/Telegram delivery queue.

## Current

- Task 017 complete. Apply migrations through `0013_notification_engine` before starting the updated API.

## Next

- Next task has not started.

## Known Issues

- Docker is unavailable in this environment, so PostgreSQL/Compose checks could not be run for tasks 013–017.
- Browser UI smoke was not completed; realtime behavior was checked through the event-bus test and frontend build, but the two-browser scenario awaits a running deployment.
- Ozon `order_number` and warehouse values are stored for filtering but upstream integration has not yet been added to populate those nullable columns.
- Real Ozon tariff mapping remains pending official field/semantics verification during integration. No money at risk is inferred from order value or rates alone.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.
- Rules for sources beyond blockers and overdue procurement have a deduplicating rule boundary but await their source data and integrations.
- NEW_ORDER, OZON_SYNC_ERROR and API_KEY_EXPIRING have a notification emission boundary but await upstream Ozon integration. Web Push and Telegram delivery adapters are deferred.

## Ozon Integration

- Not connected. Mock Mode only; no real Ozon credentials or API calls.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 48 pytest tests passed; Ruff passed (SQLite test database); Alembic upgrade through 0013 passed on SQLite.
- Frontend: ESLint, TypeScript and Vite PWA build passed using `--configLoader runner`.
- UI: notification center opened on mock data; PostgreSQL/Compose checks unavailable without Docker.
