# Ozon Production

Task 001 bootstrap of a mobile-first production management system. This version provides a status screen, a FastAPI health API, PostgreSQL wiring, Alembic, and Mock Mode flag. Orders, authentication, and real Ozon integration come in later tasks.

## Configure and run

Requires Docker Compose. Copy `.env.example` to `.env`. Set a strong `POSTGRES_PASSWORD` and use the same password in `DATABASE_URL`. Keep `OZON_MOCK_MODE=true`. For local HTTP keep `DOMAIN=:80`; for production use a real domain with DNS pointing to the VPS. Caddy will obtain HTTPS automatically for a real domain. Do not commit `.env`.

```sh
cp .env.example .env
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose ps
```

Open `http://localhost` locally (or `https://your-domain` in production). The UI reports backend state and Mock Mode. `GET /api/health` checks the API process; `GET /api/health/ready` checks database connectivity. API docs are available at `/docs` on the backend container during development; they are not exposed through Caddy in this bootstrap.

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

On Windows use `.venv\Scripts\python`, `.venv\Scripts\uvicorn`, `.venv\Scripts\pytest`, and `.venv\Scripts\ruff` instead of `./.venv/bin/...`. For a production migration use `docker compose exec backend alembic upgrade head`. The initial revision establishes migration history and deliberately creates no business tables.

Architecture and operational boundaries are described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). No real Ozon credentials are needed or used by this bootstrap.
