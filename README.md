# Ozon Production

Mobile-first production management system with authentication, RBAC, mock orders, and a production queue. Real Ozon integration is not connected.

## Production

Production uses native Debian 12 PostgreSQL/systemd/Python virtualenv/Caddy.
Start with [DEPLOYMENT.md](docs/DEPLOYMENT.md); task 034 remains pending until
actual VPS acceptance. Docker/Compose are only development/test tools.

## Development: configure and run

Requires Docker Compose. Copy `.env.example` to `.env`. Set a strong `POSTGRES_PASSWORD` and use the same password in `DATABASE_URL`. Keep `OZON_MOCK_MODE=true`. For local HTTP keep `DOMAIN=:80`; production trusted IPv4 HTTPS uses the separate native runbook. Do not commit `.env`.

```sh
cp .env.example .env
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec -it backend python -m app.cli create-admin
docker compose exec backend python -m app.cli seed-mock-orders
docker compose ps
```

Open `http://localhost` locally and sign in with the admin account. The CLI prompts for a password without displaying it. `GET /api/health` checks the API process; `GET /api/health/ready` checks database connectivity. API docs are available at `/docs` on the backend container during development; they are not exposed through Caddy.

```sh
docker compose logs -f backend caddy postgres
docker compose down
```

`seed-mock-orders` creates seven repeatable sample orders only with `OZON_MOCK_MODE=true` outside production. Run it again safely; existing samples remain untouched. `down` retains the database and other named volumes. Back up the PostgreSQL and uploads volumes before removing volumes or updating a live deployment.

## Development and checks

Use Python 3.12+ and Node.js 22+. From `backend/`:

```sh
python -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/uvicorn app.main:app --reload
./.venv/bin/pytest -q
./.venv/bin/ruff check app tests alembic
```

From `frontend/`:

```sh
npm ci
npm run dev
npm run lint
npm run typecheck
npm run build
```

On Windows use `.venv\Scripts\python`, `.venv\Scripts\uvicorn`, `.venv\Scripts\pytest`, and `.venv\Scripts\ruff` instead of `./.venv/bin/...`. Migration `0003_mock_orders` adds orders, items, status history and assignments. Set `APP_ENV=production` when serving over HTTPS so session cookies have the Secure flag. For local HTTP use `APP_ENV=development`. Use `npm run build -- --configLoader runner` on Windows if Vite's default config loader cannot access the project path.

Architecture and operational boundaries are described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). No real Ozon credentials are needed or used by this bootstrap.


### Web Push (task 018)

From `backend`, run `.venv\Scripts\python -m app.push_keys` (Linux: `.venv/bin/python -m app.push_keys`). This creates an ignored `.env.vapid` without displaying secrets or overwriting an existing key pair. Copy its three settings into the deployment's untracked `.env`, replace `VAPID_SUBJECT` with your contact `mailto:` address, and keep the private key backend-only. Retain the same key pair across deployments; rotating it requires browsers to unsubscribe and subscribe again. Apply migration `0014_web_push` before starting the API. Blank configuration disables the adapter without affecting in-app notifications.

Serve the PWA over HTTPS (localhost works for development), open Notifications, select **Включить Web Push**, then choose the event types in preferences. Enable `NEW_ORDER` to use **Тестовое уведомление**. Permission is requested only by the enable button. On iPhone, open the installed PWA. Unsupported browsers retain the in-app notification center. Subscription is per device and account; disconnect it before changing accounts on a shared device. The API accepts only HTTPS endpoints from FCM, Mozilla, Apple and Windows push services to prevent arbitrary outbound requests.

One background loop in the existing API process consumes `WEB_PUSH` rows in `notification_deliveries` every 15 seconds. Delivery rechecks active users and current preferences, uses bounded retries and records per-device receipts. HTTP 404/410 removes a subscription. Successful receipt of a provider request is delivery acceptance, not proof the OS displayed it. The stable notification tag and receipts prevent ordinary replay/retry duplicates; a process crash after provider acceptance but before the database commit can still redeliver (Web Push has no transactional exactly-once guarantee). Use one API worker, as required by the existing SSE architecture. Telegram is still deferred.

Worker event smoke: from `frontend`, run `node scripts/test-push-worker.mjs`.


Task 026 photos and codes: apply migration `0020_photos`. `UPLOAD_DIR` defaults to
`/data/uploads`, already mounted as the Compose `uploads` volume; include this volume
alongside the database in backups. `UPLOAD_MAX_BYTES` defaults to 10485760 (10 MiB).
Upload JPEG/PNG/WebP (not HEIC), up to 20 million pixels. Stored photos are JPEG at
most 1600px, without originals/EXIF. Read access requires `orders.view`, upload also
requires `comments.create` or `blockers.create`; comment photos are restricted to
the author/admin. Photo deletion is unavailable. Orders display photo galleries
and internal QR codes. Camera scan requires HTTPS (localhost is allowed for tests)
and permission; raw barcode values must equal the stored posting number. Manual
posting entry remains available. Storage writes are compensated on failed DB commits;
process crashes may leave unreferenced files, so preserve the whole uploads volume.
