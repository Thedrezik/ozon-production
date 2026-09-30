# Ozon Production

Mobile-first production management system. The current version includes authentication, users, backend RBAC, audit events, and Mock Mode. Orders and real Ozon integration come in later tasks.

## Configure and run

Requires Docker Compose. Copy `.env.example` to `.env`. Set a strong `POSTGRES_PASSWORD` and use the same password in `DATABASE_URL`. Keep `OZON_MOCK_MODE=true`. For local HTTP keep `DOMAIN=:80`; for production use a real domain with DNS pointing to the VPS. Caddy will obtain HTTPS automatically for a real domain. Do not commit `.env`.

```sh
cp .env.example .env
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec -it backend python -m app.cli create-admin
docker compose ps
```

Open `http://localhost` locally (or `https://your-domain` in production) and sign in with the admin account. The CLI prompts for a password without displaying it. `GET /api/health` checks the API process; `GET /api/health/ready` checks database connectivity. API docs are available at `/docs` on the backend container during development; they are not exposed through Caddy.

```sh
docker compose logs -f backend caddy postgres
docker compose down
```

`down` retains the database and other named volumes. Back up the PostgreSQL and uploads volumes before removing volumes or updating a live deployment.

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

On Windows use `.venv\Scripts\python`, `.venv\Scripts\uvicorn`, `.venv\Scripts\pytest`, and `.venv\Scripts\ruff` instead of `./.venv/bin/...`. The `0002_auth_rbac` migration adds user, role, permission, session, and audit tables. Set `APP_ENV=production` when serving over HTTPS so session cookies have the Secure flag. For local HTTP use `APP_ENV=development`. Use `npm run build -- --configLoader runner` on Windows if Vite's default config loader cannot access the project path.

Architecture and operational boundaries are described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). No real Ozon credentials are needed or used by this bootstrap.
