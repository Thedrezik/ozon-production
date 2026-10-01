import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api_auth import router as auth_router
from app.api_blockers import router as blockers_router
from app.api_dashboard import router as dashboard_router
from app.api_manager_tasks import router as manager_tasks_router
from app.api_money_at_risk import router as money_at_risk_router
from app.api_notifications import router as notifications_router
from app.api_orders import router as orders_router
from app.api_ozon import router as ozon_router
from app.api_procurement import router as procurement_router
from app.api_product_profiles import router as product_profiles_router
from app.api_push import router as push_router
from app.config import Settings, get_settings
from app.database import create_db_engine, database_is_ready
from app.logging import configure_logging
from app.order_events import OrderEvents
from app.ozon import create_ozon_client
from app.ozon_reconciliation import reconciliation_loop
from app.ozon_webhook import processing_loop as ozon_webhook_loop
from app.ozon_webhook import router as ozon_webhook_router
from app.telegram import configured as telegram_configured
from app.telegram import delivery_loop as telegram_delivery_loop
from app.telegram import router as telegram_router
from app.web_push import configured, delivery_loop


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    config = settings or get_settings()
    engine = create_db_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        _app.state.ozon_client = create_ozon_client(config)
        stop = asyncio.Event()
        workers = []
        if config.ozon_reconciliation_enabled:
            workers.append(asyncio.create_task(reconciliation_loop(
                engine, _app.state.ozon_client, config, _app.state.order_events, stop)))
        if config.ozon_webhook_enabled:
            workers.append(asyncio.create_task(ozon_webhook_loop(
                engine, _app.state.ozon_client, config, _app.state.order_events, stop)))
        if configured(config):
            workers.append(asyncio.create_task(delivery_loop(engine, config, stop)))
        if telegram_configured(config):
            workers.append(asyncio.create_task(telegram_delivery_loop(engine, config, stop)))
        try:
            yield
        finally:
            if workers:
                stop.set()
                await asyncio.gather(*workers)
            engine.dispose()
            _app.state.ozon_client.close()

    app = FastAPI(title="Ozon Production API", lifespan=lifespan)
    app.state.engine = engine
    app.state.secure_cookies = config.app_env == "production"
    app.state.order_events = OrderEvents()
    app.state.settings = config
    app.include_router(auth_router)
    app.include_router(orders_router)
    app.include_router(ozon_router)
    app.include_router(ozon_webhook_router)
    app.include_router(product_profiles_router)
    app.include_router(blockers_router)
    app.include_router(manager_tasks_router)
    app.include_router(procurement_router)
    app.include_router(money_at_risk_router)
    app.include_router(notifications_router)
    app.include_router(push_router)
    app.include_router(telegram_router)
    app.include_router(dashboard_router)

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
