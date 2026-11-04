"""b01: migrate applies nothing on a second run; a changed applied file stops it."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.migrate import MIGRATIONS_DIR, MigrationError, run_migrations


def _count(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM schema_migrations")).scalar_one())


def test_0001_is_applied(conn: Connection) -> None:
    names = conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
    assert "0001_foundation.sql" in names


def test_second_run_applies_nothing(test_url: str, conn: Connection) -> None:
    before = _count(conn)
    lines: list[str] = []
    assert run_migrations(test_url, log=lines.append) == []
    assert lines == ["Nothing to apply."]
    assert _count(conn) == before


def test_changed_applied_migration_stops(test_url: str, conn: Connection, tmp_path: Path) -> None:
    source = MIGRATIONS_DIR / "0001_foundation.sql"
    (tmp_path / source.name).write_bytes(source.read_bytes() + b"\n-- edited\n")
    before = _count(conn)
    with pytest.raises(MigrationError) as info:
        run_migrations(test_url, tmp_path, log=lambda _: None)
    assert str(info.value) == (
        "Applied migration 0001_foundation.sql has changed. Add a new migration instead."
    )
    assert _count(conn) == before


def test_crlf_checkout_is_not_a_change(test_url: str, migrated_db: None, tmp_path: Path) -> None:
    source = MIGRATIONS_DIR / "0001_foundation.sql"
    lf = source.read_bytes().replace(b"\r\n", b"\n")
    (tmp_path / source.name).write_bytes(lf.replace(b"\n", b"\r\n"))
    assert run_migrations(test_url, tmp_path, log=lambda _: None) == []
