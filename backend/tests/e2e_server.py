"""Run the ordinary app with migrations and isolated synthetic E2E fixtures.

No test HTTP endpoints or replacement backend. Only the external Ozon adapter
reads a local change file, allowing real webhook/reconciliation effects.
"""

import argparse
import json
import os
import re
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import uvicorn
from alembic.config import Config
from PIL import Image
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from alembic import command
from app.auth import hash_password
from app.cli import create_admin
from app.config import Settings
from app.database import create_db_engine
from app.main import create_app
from app.models import Role, TelegramAccount, User
from app.orders import seed_mock_orders
from app.ozon import MockOzonClient


class FixtureOzonClient(MockOzonClient):
    def __init__(self, changes):
        self.changes = changes

    def get_fbs(self, posting_number):
        raw = super().get_fbs(posting_number)
        raw.update(json.loads(self.changes.read_text(encoding="utf-8")))
        return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--container", action="store_true")
    args = parser.parse_args()
    # The runner owns a newly created directory. Never reset an existing DB.
    if (args.directory / "app.db").exists():
        raise RuntimeError("E2E database already exists; refusing to overwrite")
    settings = Settings()
    if settings.app_env != "test" or not settings.ozon_mock_mode:
        raise RuntimeError("E2E requires APP_ENV=test and OZON_MOCK_MODE=true")
    if args.container:
        if (not re.fullmatch(r"ozon-e2e-[a-f0-9]+", os.environ.get("E2E_PROJECT", ""))
                or args.directory != Path("/e2e") or settings.upload_dir != "/data/uploads"
                or not settings.database_url.startswith("postgresql+psycopg://")):
            raise RuntimeError("Container E2E requires an isolated generated project/PostgreSQL/uploads")
        probe = create_db_engine(settings.database_url)
        try:
            if inspect(probe).get_table_names():
                raise RuntimeError("Container E2E database must be empty; refusing existing data")
        finally:
            probe.dispose()
    else:
        expected_database = f"sqlite:///{(args.directory / 'app.db').as_posix()}"
        if settings.database_url != expected_database or Path(settings.upload_dir) != args.directory / "uploads":
            raise RuntimeError("E2E database/uploads must belong to the fresh fixture directory")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_db_engine(settings.database_url)
    with Session(engine) as db:
        create_admin("admin", "E2E Admin", "e2e-admin-password", db)
        for name, role in (("worker", "PRODUCTION_WORKER"), ("manager", "ADMIN")):
            db.add(User(username=name, display_name=f"E2E {name}",
                        password_hash=hash_password(f"e2e-{name}-password"),
                        roles=[db.scalar(select(Role).where(Role.name == role))]))
        db.commit()
        db.add(TelegramAccount(user_id=db.scalar(select(User.id).where(User.username == "admin")), chat_id="100001"))
        db.commit()
        seed_mock_orders(db)
    engine.dispose()
    Image.new("RGB", (64, 48), "blue").save(args.directory / "photo.png")
    changes = args.directory / "ozon-changes.json"
    changes.write_text("{}", encoding="utf-8")
    app = create_app(settings)
    def telegram_sender(_token, _chat, text, _url):
        with (args.directory / "telegram.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
    original_lifespan = app.router.lifespan_context
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(application):
        # Substitute only the existing external adapter, before lifespan workers
        # capture it. Routes, persistence and all domain effects stay real.
        with (patch("app.main.ManagedOzonClient", lambda _engine, _config: FixtureOzonClient(changes)),
              patch("app.telegram._telegram_request", telegram_sender)):
            async with original_lifespan(application):
                yield

    app.router.lifespan_context = lifespan
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0" if args.container else "127.0.0.1", port=args.port,
                                          access_log=False, timeout_graceful_shutdown=3))

    def shutdown():
        sys.stdin.readline()
        server.should_exit = True

    if args.container:
        # Synthetic isolated ingress only. Production source authentication is
        # unchanged and checked separately through the production Caddyfile.
        with patch("app.ozon_webhook.allowed_source", lambda request: request.app.state.settings.app_env == "test"):
            server.run()
    else:
        threading.Thread(target=shutdown, daemon=True).start()
        server.run()


if __name__ == "__main__":
    main()
