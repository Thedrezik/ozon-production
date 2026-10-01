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
- Task 017: transactional in-app notification center, per-user preferences, admin alerts, deduplication, deadline reconciliation, and Web Push/Telegram delivery queue.
- Task 018: VAPID configuration/key generation, authenticated device subscriptions, Web Push adapter on the existing queue, retries/receipts, expired-subscription cleanup, PWA push and entity links, preferences and browser fallback.
- Task 019: Telegram deep-link binding with hashed one-time codes and webhook secret, opt-in delivery through the existing notification queue, bounded retries, entity links, and unlink controls.
- Task 020: backend Seller API client/interface and offline adapter, explicit API-key connection check, bounded HTTP retries/backoff/rate-limit cooldown, typed safe errors and structured metadata logs; official contracts recorded in `OZON_API.md`.

- Task 021: explicit admin FBS v4 import via the existing client, cursor pagination, Decimal product prices, unique posting upserts, isolated production data, separate raw/tariff diagnostics, fixtures and transactional rollback tests.

## Current

- Task 021 complete. Apply migration `0016_ozon_fbs_import`. Explicit import: `POST /api/ozon/fbs/import`, session/CSRF and `settings.manage` required. No automatic Ozon requests.

## Next

- Task 022 (Ozon webhook) has not started; periodic reconciliation remains task 023.

## Known Issues

- Docker is unavailable in this environment, so PostgreSQL/Compose checks could not be run for tasks 013–021.
- Starlette emits a dependency deprecation warning about its TestClient/httpx integration; tests pass.
- Web Push UI smoke passed on mock data; actual OS push reception awaits deployment with VAPID/HTTPS. The earlier two-browser SSE scenario still awaits a running deployment.
- Real account import remains a deployment check. All automated import validation uses synthetic fixtures/mock HTTP; no live Ozon calls were made.
- Confirmed v4 tariff source data is stored separately. Mapping end deadlines and unsigned discounts to the signed normalized tariff timeline remains pending; Money at Risk does not infer amounts from prices/rates.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.
- Rules for sources beyond blockers and overdue procurement have a deduplicating rule boundary but await their source data and integrations.
- NEW_ORDER, OZON_SYNC_ERROR and API_KEY_EXPIRING have emission boundaries; task 021 adds audited explicit import only. Automated integration alerts remain future integration work.

## Ozon Integration

- Existing real client supports `/v1/roles` and current `/v4/posting/fbs/list`; official v4 contract rechecked in the browser on 2026-10-01. Mock Mode remains default; imports can run offline using v4 fixtures. No live account requests were performed. See `OZON_API.md`.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: 126 pytest tests passed, including 22 FBS import tests and 42 client tests. Ruff passed (`cd backend; python -m ruff check --isolated app tests alembic`). Fixtures/mock HTTP only.
- Import: primary/repeated/existing-production import, external updates, preservation of production relationships/history/override, multiple products, unknown/missing optional fields, exact raw JSON/Decimal, currency/range safety, no duplicates, cursors/retries, RBAC/CSRF and transaction rollback covered.
- Database: SQLite Alembic upgrade/downgrade/upgrade through `0016_ozon_fbs_import` and new columns/table verified. Docker/PostgreSQL unavailable.
- Health: `/api/health` and `/api/health/ready` returned 200 in TestClient on SQLite.
- Frontend: unchanged in task 021; previous lint/typecheck/PWA build passed. No new frontend checks required.
