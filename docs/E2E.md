# Task 033: end-to-end tests

Run the whole suite from the repository's `frontend` directory:

```sh
npm run test:e2e
```

This builds the actual production PWA, then runs six scenarios on **desktop
1440×1000** and **mobile 390×844** (touch/mobile browser settings). Both use
Europe/Moscow. The command returns nonzero for any failure; no test retries.

## Prerequisites

- Node and `npm ci` in `frontend` (Playwright is a locked development dependency).
- Python 3.12+ virtual environment in `backend/.venv`, with
  `backend/requirements-dev.txt` installed. Override its executable using
  `E2E_PYTHON` if needed.
- Windows: installed Microsoft Edge is used automatically. Linux: install the
  matching Chromium with `npx playwright install --with-deps chromium` in
  `frontend`. `E2E_BROWSER_CHANNEL` can select an installed supported channel.
- `PLAYWRIGHT_MODULE` can point to an existing bundled Playwright `index.mjs`,
  following the project's earlier browser-test convention.

For a focused diagnostic run after building, `E2E_FILTER` is a substring of
`desktop: production workflow`, etc. Leave it unset for the full suite.

## Actual application, isolated data

Each scenario starts the existing `create_app` FastAPI application under Uvicorn,
applies **all Alembic migrations**, runs the existing `seed_mock_orders`, and uses
the existing admin bootstrap/password/RBAC code to create synthetic admin,
manager and worker accounts. It gets a fresh temporary SQLite database and uploads
directory. The harness refuses to overwrite an existing database. It checks
`/api/health` (Mock Mode) and `/api/health/ready` before opening the browser.

The Node HTTP server serves `frontend/dist`, including the generated service
worker, and streams `/api/*` to that real backend. It implements no business API
responses. Cookies, CSRF, RBAC, transitions, transactions, audit, photos,
notifications and SSE all run through the application. Separate browser contexts
represent admin/manager/worker, sharing only the test backend.

Only the **external Ozon adapter** is replaced with a subclass of the existing
`MockOzonClient`. It uses the existing Seller fixtures and reads a local synthetic
change file for webhook scenarios. Import and durable webhook processing run
through the real HTTP endpoints; reconciliation invokes the existing service in
a separate CLI process against the same database (there is no reconciliation
HTTP endpoint). No test endpoints or alternative backend are added.

The transport proxy can inject a 503 outage, disable SSE, or hold a claim until
a real competing assignment commits. The last barrier makes the 409 scenario
deterministic without depending on a scheduling race. These are transport/concurrency
controls, not mocked domain results.

Mock Mode/test environment and isolated database paths are forced. Ozon credentials,
Telegram and VAPID settings are cleared; external delivery is disabled. Tests never
connect to real Ozon, Telegram or Web Push. Existing backend suites cover their
fake transports; browser tests verify real in-app notifications/receipts.

Contexts close before graceful backend shutdown; only the newly generated temporary
directory is removed. Existing `.env`, database, uploads and Compose volumes are
never reset. Concurrent runs get distinct ports/directories. Tests are sequential
within each run to keep resource use small.

## Coverage (each scenario runs at both viewports)

| Scenario | Assertions |
| --- | --- |
| Production workflow | Admin dashboard and clickable Money at Risk drill-down; worker manual QR lookup, claim and production; blocker; another manager session receives actual SSE and sees its automatic task; notification/read receipt; manager claims task and cannot resolve before source; linked procurement through UI, ORDERED/PURCHASED/DELIVERED and history; blocker IN_PROGRESS/RESOLVED; automatic task resolution and restoration of IN_PRODUCTION; PRODUCED/QUALITY_CHECK/PACKING/READY_TO_SHIP; timeline/audit/analytics/dashboard and priority/risk changes. |
| Auth/RBAC | UI login/logout, session invalidation and offline cleanup; worker navigation restrictions, real API 403 for management/finance/audit/analytics reads and admin/bulk/assignment writes; unchanged order after denial. |
| Queue/files | Combined search/status filter, two-order bulk assignment and audit; UI comment; synthetic PNG upload through the file input, compressed/authenticated JPEG; generated QR; valid/unknown manual code; no horizontal overflow. |
| PWA/live fallback | Real service worker, same-tab offline reload and stale read-only queue, no mutations or deferred replay; server changes while disconnected and fresh reconnect; focus fallback with SSE disabled; no API entries in CacheStorage. |
| Ozon changes | Existing mock import and idempotent reimport; durable deadline webhook; repeated cancellation webhook, independent internal status/history, archived P4, one cancellation task, blocked production continuation; manager task resolution; real reconciliation freshness; integration UI smoke. |
| Conflict/offline safeguards | Actual competing assignment returns 409 and refreshes UI; API outage with navigator online; offline deletion; one-hour snapshot expiry; user deactivation during disconnection and rejected session on reconnect. |

The seeded tariff is Decimal-backed: `-120 → 0 → 350` produces **470 RUB** of
potential future exposure. Blocker creation moves it to BLOCKED_RISK; resolution
removes that category. READY_TO_SHIP still retains shipment tariff exposure until
shipment, consistent with the existing product rules. UI procurement uncovered a
SQLite UTC serialization issue: order timestamps now retain timezone information
on API round trips, with a backend regression test.

Waits observe API/UI state rather than fixed sleeps. Reconnect allows the existing
30-second recovery polling contract, plus request time. SSE and explicit focus
fallback are checked separately. Failures print scenario/assertion details and save
screenshots, DOM, traces and backend logs under ignored `frontend/e2e-results/`.
Successful cases discard traces and save no screenshots. Artifacts contain only
synthetic test accounts/data; keep them out of Git. View a failure trace with
`npx playwright show-trace <path-to-trace.zip>`.

## Verification boundary for task 034

Task 034 adds the opt-in native Linux container runner:

```sh
E2E_CONTAINER=true E2E_PROBE=true npm run test:e2e
```

It reuses every scenario against fresh PostgreSQL/backend/Caddy/PWA volumes,
validates mounts before startup/cleanup and rejects non-empty databases. Test-only
fault proxy handles outage/SSE/claim barriers; only the external adapter and local
webhook-source check are relaxed in fixtures. Caddy serves actual static assets
over local internal-CA HTTPS. Certificate verification is disabled only in this
generated loopback fixture, APP_ENV=test retains development cookie semantics;
public TLS/Secure cookies and unmodified production source protection require the
separate launch checks in [DEPLOYMENT.md](DEPLOYMENT.md).

E2E_PROBE writes synthetic actual-query EXPLAIN ANALYZE/index/migration/concurrency,
DB connections, Docker CPU/cgroup memory and per-process RSS reports to ignored
deployment-results. Fixtures are small and do not establish realistic VPS capacity.
This runner is implemented but **not executed here**, because supported Docker
daemon access is unavailable. Run it on a Linux test host with enough build/browser
memory; the mandatory restore drill must also run on the actual target VPS.

Docker is not available in the task 033 agent environment. Local E2E executes the
real application and migrations with SQLite, not PostgreSQL/Caddy. Task 034 must
repeat the workflows against an isolated Docker Compose environment on Linux,
apply migrations and mock seed, check both health endpoints, and validate PostgreSQL
locking/constraints, Caddy HTTPS/proxy/SSE and resource limits. Do not point this
local reset harness at an existing deployment/database. An isolated container
runner is a remaining task 034 deployment check, not a claimed result here.

Real phone camera, installation/offline PWA behavior on physical devices, actual
OS Web Push/Telegram reception, real Ozon credentials and ingress checks require
the HTTPS deployment. No external production endpoints belong in automated E2E.
The mandatory isolated Linux backup → modify → restore → verify drill remains
the existing task 034 launch gate.
