# PROJECT STATE

Last updated: 2026-10-02

## Completed

- Task 030: PostgreSQL/uploads backups, retention, guarded transactional DB restore, staged uploads restore, Linux operations guide and automated checks. Backup creation confirmed by user's real Docker run on Windows; final Linux restore drill is a mandatory task 034 production-launch gate.
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

- Task 028: SQL production analytics, local-date period filter, stage/cycle averages, deadline-cohort overdue, blocker reasons, SKU/offer actual averages with existing normative profiles, actor-based employee throughput, current assignment workload, pagination and RBAC; migration `0021_analytics`.

- Task 029: existing audit extended with transactional safe old/new snapshots, actor/IP/User-Agent, immutable ORM/PostgreSQL guards, critical-action coverage, audit.view API and mobile filtered paginated viewer; migration `0022_audit`.

## Current

- Task 030 completed by user-approved verification boundary. Windows manual drill debugging stopped; full destructive Linux restore verification moved to task 034 before production launch. Migration head: `0022_audit`. No commit or push.

## Next

- Await a separate task request; do not begin task 031. Task 034 must pass the mandatory isolated Linux VPS backup → modify → restore → verify gate before production launch.

## Known Issues

- Full PostgreSQL restore remains unverified on the target Linux VPS: mandatory task 034 launch gate. User's Windows Docker run confirmed unique isolated volumes, migrations, PostgreSQL/uploads archive creation, publication to /data/backups and isolated failure cleanup. Windows harness stopped at `Unexpected backup bundle members`; full Windows restore is non-authoritative because of PowerShell/Git Bash/MSYS compatibility. Docker/Caddy/shellcheck unavailable in the agent environment. Real Ozon connection/delivery remains an HTTPS deployment check.
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

- Task 030: Bash syntax and synthetic checks passed (archive creation/structure, newest-file retention, confirmation, guarded --yes, DB/utility/validation failures, uploads restore and corrupted-stream rollback). PowerShell regression passed (stdin filename/transaction checks, 18 Compose calls, 4 root Docker calls and production guards). git diff --check passed. User-confirmed real Windows Docker backup creation; full Linux restore deferred to mandatory task 034 acceptance.
- Task 029: full backend suite 213 passed; focused audit/auth 15 passed (7 audit cases). Ruff app/tests/Alembic passed. Existing Starlette/httpx and Alembic deprecation warnings remain.
- Frontend lint/typecheck/production build and headless Edge mobile mock audit UI passed: all filters, pagination, old/new detail, empty state and audit.view visibility. git diff --check passed.
- Alembic upgrade/downgrade/upgrade and audit columns/indexes verified on SQLite. PostgreSQL SQL generation for 0021_analytics → 0022_audit and downgrade passed, including append-only UPDATE/DELETE/TRUNCATE trigger. Older rows are preserved without fabricated snapshots.
- Docker unavailable: Compose build/up, container migration/ps, actual PostgreSQL schema/trigger execution and container health/readiness were not run. Health/readiness backend tests pass; apply migration before deployment.
