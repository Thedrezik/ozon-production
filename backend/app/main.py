import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api_auth import router as auth_router
from app.config import Settings, get_settings
from app.database import create_db_engine, database_is_ready
from app.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    config = settings or get_settings()
    engine = create_db_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Ozon Production API", lifespan=lifespan)
    app.state.engine = engine
    app.state.secure_cookies = config.app_env == "production"
    app.include_router(auth_router)

    @app.get("/api/health")
    def health() -> dict[str, str | bool]:
        return {"status": "ok", "mock_mode": config.ozon_mock_mode}

    @app.get("/api/health/ready")
    def ready() -> dict[str, str]:
        try:
            database_is_ready(engine)
        except SQLAlchemyError:
            logging.getLogger(__name__).exception("Database readiness check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from None
        return {"status": "ready"}

    return app


app = create_app()
