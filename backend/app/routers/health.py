"""GET /api/health: is the API up, can it reach the database, which migration is last.
In production the migration name is left out."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.engine import get_engine

logger = logging.getLogger("app")

router = APIRouter()

_LAST_MIGRATION = text("SELECT filename FROM schema_migrations ORDER BY filename DESC LIMIT 1")


def _answer(content: dict[str, Any], status_code: int = 200) -> JSONResponse:
    if get_settings().app_env == "production":
        content.pop("migrations")
    return JSONResponse(status_code=status_code, content=content)


@router.get("/health")
def health(engine: Engine = Depends(get_engine)) -> JSONResponse:
    try:
        with engine.connect() as conn:
            last = conn.execute(_LAST_MIGRATION).scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.warning("Health check could not reach the database (%s)", type(exc).__name__)
        return _answer({"status": "error", "database": "down", "migrations": None}, status_code=503)
    return _answer({"status": "ok", "database": "ok", "migrations": last})
