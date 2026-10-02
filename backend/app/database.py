from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str) -> Engine:
    from app.audit import install_audit

    install_audit()
    if database_url.startswith("sqlite:"):
        engine = create_engine(database_url, hide_parameters=True)
        engine._audit_enabled = True
        return engine
    engine = create_engine(
        database_url,
        hide_parameters=True,
        pool_size=2,
        max_overflow=1,
        pool_timeout=3,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    engine._audit_enabled = True
    return engine


def database_is_ready(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
