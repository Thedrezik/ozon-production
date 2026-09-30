from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:"):
        return create_engine(database_url)
    return create_engine(
        database_url,
        pool_size=2,
        max_overflow=1,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def database_is_ready(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
