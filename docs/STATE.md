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
- Task 022: verified Ozon FBS/rFBS push endpoint and TYPE_PING handshake, durable event inbox, idempotency, restart-safe processing/retries, shared get/upsert, cancellation manager tasks, existing notifications/projections and post-commit SSE.

## Current

- Task 022 complete. Apply migration `0017_ozon_webhook` before setting `OZON_WEBHOOK_ENABLED=true`. Endpoint: `POST /api/ozon/webhook`; behind Caddy configure its trusted proxy peer. Failed-event retry requires `settings.manage`/CSRF. No periodic order sync.

## Next

- Task 023: periodic reconciliation; not started.

## Known Issues

- Docker/Caddy executables are unavailable here; PostgreSQL/Compose and Caddy runtime checks could not be run for task 022. Real Ozon connection/delivery remains an HTTPS deployment check.
- Starlette emits a dependency deprecation warning about its TestClient/httpx integration; tests pass.
- Web Push UI smoke passed on mock data; actual OS push reception awaits deployment with VAPID/HTTPS. The earlier two-browser SSE scenario still awaits a running deployment.
- Real account import remains a deployment check. All automated import validation uses synthetic fixtures/mock HTTP; no live Ozon calls were made.
- Confirmed v4 tariff source data is stored separately. Mapping end deadlines and unsigned discounts to the signed normalized tariff timeline remains pending; Money at Risk does not infer amounts from prices/rates.
- Photo upload infrastructure is not yet available; blocker responses reserve a `photos` field.
- Rules for sources beyond blockers and overdue procurement have a deduplicating rule boundary but await their source data and integrations.
- Task 022 emits NEW_ORDER, ORDER_CANCELLED and processing-error alerts through the existing engine. API_KEY_EXPIRING remains a future integration rule.

## Ozon Integration

- Existing real client supports `/v1/roles`, current `/v4/posting/fbs/list` and `/v3/posting/fbs/get`. Push payloads, handshake, responses, retries and source networks verified in official browser docs on 2026-10-01. Mock Mode remains default, webhook disabled by default; fixture/mock HTTP tests only. See `OZON_API.md`.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend: all 159 pytest tests passed; Ruff passed (`cd backend; .venv/Scripts/python.exe -m ruff check --isolated app tests alembic`). All Ozon coverage uses fixtures/mock HTTP.
- Webhook: 33 added tests cover receipt/handshake, new/existing postings, status/cancellation/date changes, concurrent duplicates, notification/task deduplication, malformed/unknown payloads, source/seller checks, atomic rollback, retries/replay RBAC, restart recovery, response during slow API calls and risk refresh.
- Database: SQLite Alembic upgrade/downgrade/upgrade through `0017_ozon_webhook`, inbox uniqueness and delivery columns verified. Docker/PostgreSQL unavailable.
- Health: `/api/health` and `/api/health/ready` returned 200 in TestClient on SQLite.
- Frontend unchanged; no frontend checks required. Known Starlette/httpx and Alembic path-separator deprecation warnings only.
