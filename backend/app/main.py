import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api_analytics import router as analytics_router
from app.api_audit import router as audit_router
from app.api_auth import router as auth_router
from app.api_blockers import router as blockers_router
from app.api_dashboard import router as dashboard_router
from app.api_manager_tasks import router as manager_tasks_router
from app.api_money_at_risk import router as money_at_risk_router
from app.api_notifications import router as notifications_router
from app.api_orders import router as orders_router
from app.api_ozon import router as ozon_router
from app.api_ozon_credentials import router as credentials_router
from app.api_procurement import router as procurement_router
from app.api_product_profiles import router as product_profiles_router
from app.auth import Current, LoginLimiter
from app.config import Settings, get_settings
from app.database import create_db_engine, database_is_ready
from app.features import enabled
from app.logging import configure_logging
from app.order_events import OrderEvents
from app.ozon_credentials import ManagedOzonClient, expiration_loop
from app.ozon_reconciliation import reconciliation_loop
from app.ozon_webhook import processing_loop as ozon_webhook_loop
from app.ozon_webhook import router as ozon_webhook_router
from app.security import SECURITY_HEADERS, SecurityMiddleware, production_host
from app.storage import LocalStorage
from app.telegram import configured as telegram_configured
from app.telegram import delivery_loop as telegram_delivery_loop
from app.telegram import router as telegram_router


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    configure_logging(config)
    engine = create_db_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        _app.state.ozon_client = ManagedOzonClient(engine, config)
        stop = asyncio.Event()
        workers = []
        if enabled(config, "key_expiration"):
            workers.append(asyncio.create_task(expiration_loop(engine, config, stop)))
        if config.ozon_reconciliation_enabled:
            workers.append(asyncio.create_task(reconciliation_loop(
                engine, _app.state.ozon_client, config, _app.state.order_events, stop)))
        if config.ozon_webhook_enabled:
            workers.append(asyncio.create_task(ozon_webhook_loop(
                engine, _app.state.ozon_client, config, _app.state.order_events, stop)))
        if enabled(config, "web_push"):
            from app.web_push import configured, delivery_loop

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

    production = config.app_env == "production"
    app = FastAPI(title="Ozon Production API", lifespan=lifespan,
                  docs_url=None if production else "/docs",
                  redoc_url=None if production else "/redoc",
                  openapi_url=None if production else "/openapi.json")
    if production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[production_host(config)], www_redirect=False)
    app.add_middleware(SecurityMiddleware, settings=config)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, _error):
        # Pydantic's default response echoes input values, including passwords/keys.
        return JSONResponse({"detail": "Invalid request data"}, status_code=422)

    @app.exception_handler(Exception)
    async def internal_error(_request, _error):
        logging.getLogger(__name__).error("Request failed")
        headers = dict(SECURITY_HEADERS)
        if production:
            headers["Strict-Transport-Security"] = "max-age=31536000"
        return JSONResponse({"detail": "Internal server error"}, status_code=500, headers=headers)
    app.state.engine = engine
    app.state.login_limiter = LoginLimiter()
    app.state.secure_cookies = config.app_env == "production"
    app.state.order_events = OrderEvents()
    app.state.settings = config
    app.state.storage = LocalStorage(config.upload_dir)
    app.state.upload_slot = asyncio.Semaphore(1)
    app.include_router(audit_router)
    if enabled(config, "photos") or enabled(config, "scanner"):
        from app.api_files import router as files_router

        app.include_router(files_router)
    app.include_router(auth_router)
    app.include_router(orders_router)
    app.include_router(ozon_router)
    app.include_router(credentials_router)
    app.include_router(ozon_webhook_router)
    app.include_router(product_profiles_router)
    app.include_router(blockers_router)
    if enabled(config, "manager_tasks"):
        app.include_router(manager_tasks_router)
    if enabled(config, "procurement"):
        app.include_router(procurement_router)
    app.include_router(money_at_risk_router)
    app.include_router(notifications_router)
    if enabled(config, "web_push"):
        from app.api_push import router as push_router

        app.include_router(push_router)
    app.include_router(telegram_router)
    app.include_router(dashboard_router)
    if enabled(config, "analytics"):
        app.include_router(analytics_router)

    @app.get("/api/features")
    def features(_current: Current):
        return {"optional": config.enabled_optional_features.split(",") if config.enabled_optional_features else [],
                "timezone": config.organization_timezone}

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
