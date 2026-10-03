# Architecture — simplified core, task 036

Current behavior is specified in [CORE_WORKFLOW.md](CORE_WORKFLOW.md).
Single PostgreSQL + FastAPI/Uvicorn worker + static React PWA/Caddy; no broker.
Existing pool 2+1 and memory caps 256/384/96 MiB remain.

- Webhook → validated durable inbox → existing get/upsert + real tariff adapter →
  atomic domain effects/history/Notification → commit → SSE.
- Reconciliation: startup + 900 s after completion, same import/upsert/lock;
  bounded known-posting backfill, no cancellation inferred from missing data.
- Atomic claim starts IN_PRODUCTION; PRODUCED → READY_TO_SHIP; external Ozon
  confirms HANDED_TO_SHIPPING. Preserve status enum/legacy data.
- Simple Blocker saves/restores stage; resolution stores actor/time/comment.
  Cancellation before start is history only; after start blocks workflow,
  stays critical until admin disposition and queues Telegram.
- Priority/Tariff/Money at Risk are Decimal read-time projections, not background
  aggregates. No autonomous deadline notification scheduler.
- Existing NotificationDelivery sends three core alert types to linked admins;
  existing dedupe/retries/linking remain. Provider/commit crash gap remains.
- Validated ENABLED_OPTIONAL_FEATURES defaults empty; routers, source tasks,
  procurement/load evaluations, Push/key-expiry loops and frontend lazy chunks
  are gated. See OPTIONAL_FEATURES.md for dependencies and re-enabling.
- One SSE session stream, authenticated reconnect without open refresh; one
  shared 60 s fallback/clock refresh and focus/online recovery. API NetworkOnly,
  epoch/revision detects reconnect gaps/restarts and invalidates only changed data;
  bounded read-only offline snapshot. Optional chunks excluded from core precache.
- Security task 031/audit/backup preserved. Credential SELECT releases its DB slot
  before HTTP; domain delivery/import transactions still need slow-provider/pool
  capacity validation on Linux. Task 034 remains pending; no deployment in 036.

The original bootstrap description below is preserved as historical context;
its future/optional/default statements are superseded by this section.

<details><summary>Historical bootstrap architecture</summary>

The recommended minimum production deployment is a dedicated Linux VPS with 1 CPU and 1 GB RAM. Docker Compose runs PostgreSQL, one FastAPI/Uvicorn process, and Caddy. Caddy serves the compiled React PWA and proxies `/api/*` to FastAPI. Only Caddy exposes public ports. PostgreSQL and the API stay on the Compose network. Task 034 preserves all existing functions and the small database pool; lightweight review is a later separate stage. Actual target capacity remains an acceptance check.

## Components and data

- **Frontend:** React, TypeScript, Vite and Tailwind. The mobile-first shell shows connectivity and Mock Mode. The service worker caches only static shell assets; API requests always use the network and the UI makes offline state explicit.
- **Backend:** FastAPI application factory, Pydantic settings, SQLAlchemy 2 engine and Alembic migrations. One Uvicorn worker and a small database pool fit the target VPS. `/api/health` is a process liveness check; `/api/health/ready` checks PostgreSQL with `SELECT 1`.
- **Database:** PostgreSQL owns operational data. User, role, permission, session and audit tables are present. Ozon's logistics status and the internal production status will be separate fields and histories. Money will use `Decimal`/`NUMERIC`, timestamps UTC, and organization timezone only for display.
- **Ozon boundary:** a future Ozon client interface will have a mock implementation and a real implementation. `OZON_MOCK_MODE=true` is the bootstrap default. No Ozon credentials, network calls, webhook endpoint or sample orders are used in task 001. Before implementing the real client, verify current official Ozon Seller API documentation.

## Planned flows

- **Webhook:** Ozon → validated FastAPI handler → idempotency check and transactional database update → realtime UI event. A duplicate event must not create duplicate orders or actions. Actual payload, verification, and event types depend on official API documentation.
- **Reconciliation:** a lightweight scheduled job → Ozon client → paginated comparison and transactional upserts. It recovers missed webhook events. A single-process scheduler is sufficient initially; deployment must ensure only one scheduler instance.
- **Authentication and RBAC:** server-side sessions use opaque HttpOnly cookies, scrypt password hashes, a per-session CSRF token, and backend permission checks. Frontend visibility alone never grants access. The single API worker limits failed logins in memory. Audit events record access and user changes. A CLI creates the first super admin; admins create later users.
- **Notifications:** future domain events create in-app notifications first; optional Web Push and Telegram delivery consume those events without becoming the primary workflow.
- **Files:** authenticated upload service stores compressed, validated images in a persistent local volume (`/data/uploads`), with metadata in PostgreSQL. A storage interface will permit changing the backend later.

## Operations

Caddy terminates HTTPS for a real domain. PostgreSQL, uploads, and backups use persistent volumes. The backup plan is a regular `pg_dump` plus uploads archive copied off the VPS, with periodic restore drills. Secrets live in an untracked `.env` or deployment secret store, never in the frontend bundle or git. Database migrations are explicit via Alembic before new code is put into service.

</details>
