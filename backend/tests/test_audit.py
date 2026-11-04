"""b02: audit_log is append-only. b06: write_audit shares the caller's transaction."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.audit import Actor, write_audit

ACTOR = Actor(id=uuid4(), name="Test Admin", role="admin", ip="127.0.0.1")

_INSERT = text(
    "INSERT INTO audit_log (by_name, by_role, action, detail) "
    "VALUES ('Test Admin', 'admin', 'test.append_only', 'row for append-only test') RETURNING id"
)


def _count(conn: Connection, action: str) -> int:
    query = text("SELECT count(*) FROM audit_log WHERE action = :action")
    return int(conn.execute(query, {"action": action}).scalar_one())


def _fails(conn: Connection, sql: str, params: dict[str, Any]) -> str:
    with pytest.raises(DBAPIError) as info:
        with conn.begin_nested():
            conn.execute(text(sql), params)
    return str(info.value.orig)


def test_insert_audit_row_works(conn: Connection) -> None:
    row_id: UUID = conn.execute(_INSERT).scalar_one()
    found = conn.execute(text("SELECT count(*) FROM audit_log WHERE id = :id"), {"id": row_id})
    assert found.scalar_one() == 1


def test_update_and_delete_audit_row_fail(conn: Connection) -> None:
    row_id: UUID = conn.execute(_INSERT).scalar_one()
    error = _fails(conn, "UPDATE audit_log SET detail = 'changed' WHERE id = :id", {"id": row_id})
    assert "can never be changed or deleted" in error
    error = _fails(conn, "DELETE FROM audit_log WHERE id = :id", {"id": row_id})
    assert "can never be changed or deleted" in error


def test_write_audit_writes_one_row(conn: Connection) -> None:
    action = f"test.audit.{uuid4()}"
    write_audit(conn, ACTOR, action, "one row")
    row = conn.execute(
        text("SELECT by_id, by_name, by_role, detail, ip FROM audit_log WHERE action = :action"),
        {"action": action},
    ).one()
    assert tuple(row) == (ACTOR.id, "Test Admin", "admin", "one row", "127.0.0.1")


def test_rolled_back_transaction_leaves_no_audit_row(conn: Connection) -> None:
    action = f"test.audit.{uuid4()}"
    nested = conn.begin_nested()
    write_audit(conn, ACTOR, action, "will be rolled back")
    assert _count(conn, action) == 1
    nested.rollback()
    assert _count(conn, action) == 0
