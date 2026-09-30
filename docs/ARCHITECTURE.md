# Architecture (bootstrap)

The first deployment is one small Linux VPS (about 1 CPU and 1 GB RAM). Docker Compose runs PostgreSQL, one FastAPI/Uvicorn process, and Caddy. Caddy serves the compiled React PWA and proxies `/api/*` to FastAPI. Only Caddy exposes public ports. PostgreSQL and the API stay on the Compose network.

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
- **Files:** future upload service stores compressed, validated images in a persistent local volume (`/data/uploads`), with metadata in PostgreSQL. A storage interface will permit changing the backend later.

## Operations

Caddy terminates HTTPS for a real domain. PostgreSQL, uploads, and backups use persistent volumes. The backup plan is a regular `pg_dump` plus uploads archive copied off the VPS, with periodic restore drills. Secrets live in an untracked `.env` or deployment secret store, never in the frontend bundle or git. Database migrations are explicit via Alembic before new code is put into service.
