"""Database connection for the application (DATABASE_URL only)."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection

from app.config import get_settings


def sqlalchemy_url(url: str) -> str:
    """Make SQLAlchemy use psycopg 3 for a plain postgresql:// URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def libpq_url(url: str) -> str:
    """Turn a SQLAlchemy URL into one psycopg.connect accepts."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def make_engine(url: str) -> Engine:
    # hide_parameters keeps statement values (such as secrets) out of error messages and logs.
    return create_engine(
        sqlalchemy_url(url),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def get_conn() -> Iterator[Connection]:
    """One connection and one transaction per request: commit on success, roll back on error."""
    with get_engine().begin() as conn:
        yield conn
