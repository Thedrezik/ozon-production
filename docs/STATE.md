# PROJECT STATE

Last updated: 2026-10-02

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

- Task 023: lifespan reconciliation via shared v4 cursor import/upsert and webhook effects, missing-posting get backfill, isolated mock/real sync state, deduplicated outage notifications/tasks, recovery, freshness banner and post-commit SSE.
- Task 024: shared cancellation/date-change effects across import, webhook and reconciliation; cancelled queue/archive rules, responsible-worker alerts, stage-aware Manager Tasks, safe old/new audit/timeline, deadline notice retirement and read-time priority/risk refresh. Production history remains intact.

- Task 025: encrypted authoritative credentials, real-client validation before rotation, admin integration status, UTC expiration settings, source-keyed alerts/critical tasks, safe audit and shared runtime refresh.

- Task 026: local storage interface, bounded validated/compressed photos for orders/blockers/comments, authenticated galleries, audit/timeline, posting QR and PWA camera barcode lookup.

- Task 027: short-lived tab-scoped read-only offline queue, cached-shell reload, explicit OFFLINE/stale/time display, session-checked reconnect/server refresh, conflict feedback and automated production-PWA browser checks.

## Current

- Task 027 complete. Read-only offline strategy documented in DECISIONS.md. Migration head unchanged: `0020_photos`. No commit or push.

## Next

- Task 027 finished; task 028 has not been started.

## Known Issues

- Docker/Caddy executables are unavailable here; PostgreSQL/Compose and Caddy runtime checks could not be run for task 027. Real Ozon connection/delivery remains an HTTPS deployment check.
- Starlette emits a dependency deprecation warning about its TestClient/httpx integration; tests pass.
- Web Push UI smoke passed on mock data; actual OS push reception awaits deployment with VAPID/HTTPS. The earlier two-browser SSE scenario still awaits a running deployment.
- Real account import remains a deployment check. All automated import validation uses synthetic fixtures/mock HTTP; no live Ozon calls were made.
- Confirmed v4 tariff source data is stored separately. Mapping end deadlines and unsigned discounts to the signed normalized tariff timeline remains pending; Money at Risk does not infer amounts from prices/rates.
- Physical phone camera/HTTPS PWA validation remains a deployment check. Automated mobile UI and synthetic camera QR scanning passed. HEIC/HEIF is unsupported; upload JPEG, PNG or WebP.
- Additional integration/manager automation rules await their source data and later tasks; reconciliation errors and cancellation-after-start already use source-keyed tasks.
- Initial unknown postings older than the configured discovery window (30 days) require the existing historical importer. Outage discovery is capped at the verified 365-day API window; known nonterminal postings are checked independently. API_KEY_EXPIRING now uses the encrypted credential expiration configuration.

- Offline queue retains only the last loaded page for up to one hour in the same tab; a new tab needs a network queue load. No offline login, filters, details, photos or mutation queue. Private-device use remains necessary for local display snapshots.

## Ozon Integration

- Existing real client supports `/v1/roles`, current `/v4/posting/fbs/list` and `/v3/posting/fbs/get`. Push payloads, handshake, responses, retries and source networks verified in official browser docs on 2026-10-01. Mock Mode remains default, webhook disabled by default; fixture/mock HTTP tests only. See `OZON_API.md`.

## Deployment

- Production VPS not deployed. Apply `alembic upgrade head` before starting the updated API.

## Last Tests

- Backend full suite: 202 passed, including auth/RBAC, status conflicts and health/readiness. Ruff app/tests/Alembic passed (run from backend).
- Frontend lint/typecheck/production build, offline snapshot unit checks, push-worker checks and git diff --check passed. Build required sandbox escalation for esbuild directory reads.
- Headless Edge with the actual production build/generated service worker and synthetic local mock API: offline reload/shell/cached queue, OFFLINE + unchanged timestamp/stale warning, reconnect + fresh backend data, no deferred writes, live 409 refresh/message, backend outage while browser stays online, auth revocation/cleanup, offline deletion and no API cache all passed.
- Docker executable is unavailable: Compose build/up, container Alembic, ps and container health/readiness were not run. No backend/migration change in task 027. Existing Starlette/httpx and Alembic dependency deprecation warnings remain.
