"""Audit-log writer. Uses the caller's connection, so the audit row commits or
rolls back together with the change it records."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.licence import Module

Role = Literal["super_admin", "admin", "finance", "applicant"]


@dataclass(frozen=True)
class Actor:
    id: UUID | None
    name: str
    role: Role | None
    ip: str | None = None
    sections: tuple[Module, ...] = ()


_INSERT_AUDIT = text(
    "INSERT INTO audit_log (by_id, by_name, by_role, action, detail, ip) "
    "VALUES (:by_id, :by_name, :by_role, :action, :detail, :ip)"
)


def write_audit(conn: Connection, actor: Actor, action: str, detail: str) -> None:
    conn.execute(
        _INSERT_AUDIT,
        {
            "by_id": actor.id,
            "by_name": actor.name,
            "by_role": actor.role,
            "action": action,
            "detail": detail,
            "ip": actor.ip,
        },
    )
