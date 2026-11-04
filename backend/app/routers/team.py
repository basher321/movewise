"""The admin team (super admin only). Admins are never deleted; there is no delete endpoint.

Rules as F10 and the mock: approving gives role admin with all licensed sections; changing
the role to finance clears sections; the last active super_admin can never be deactivated or
demoted (CONFLICT); nobody can change their own role or deactivate themselves (FORBIDDEN);
deactivating ends all that admin's sessions.
"""

import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.accounts import ADMIN_COLUMNS, admin_view
from app.auth.deps import require_admin, require_super_admin
from app.auth.passwords import hash_password
from app.auth.sessions import end_admin_sessions
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULES, read_licence

router = APIRouter()

ADMIN_ROLES = ("super_admin", "admin", "finance")
# Key of the transaction lock that makes team changes run one at a time.
TEAM_LOCK = 3_000_002

_COLUMNS = ", ".join(ADMIN_COLUMNS)
_LIST = text(f"SELECT {_COLUMNS} FROM admin_users ORDER BY created_at, id")
_FIND = text(f"SELECT {_COLUMNS} FROM admin_users WHERE id = :id FOR UPDATE")
_ACTIVE_SUPER_ADMINS = text(
    "SELECT count(*) FROM admin_users WHERE role = 'super_admin' AND approved AND active"
)
_APPROVE = text(
    "UPDATE admin_users SET approved = true, role = 'admin', sections = CAST(:sections AS text[]) "
    f"WHERE id = :id RETURNING {_COLUMNS}"
)
_SET_PASSWORD = text("UPDATE admin_users SET password_hash = :password_hash WHERE id = :id")
# The same easy-to-read letters as the applicant reset (no 0/o, 1/l/i).
TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_SET_ACTIVE = text(f"UPDATE admin_users SET active = :active WHERE id = :id RETURNING {_COLUMNS}")
_SET_ROLE = text(
    "UPDATE admin_users SET role = :role, sections = CAST(:sections AS text[]) "
    f"WHERE id = :id RETURNING {_COLUMNS}"
)
_SET_SECTIONS = text(
    f"UPDATE admin_users SET sections = CAST(:sections AS text[]) WHERE id = :id RETURNING {_COLUMNS}"
)


class RoleIn(BaseModel):
    role: str


class SectionsIn(BaseModel):
    sections: list[str]


def _not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Admin not found.")


def _find(conn: Connection, admin_id: str) -> RowMapping:
    try:
        uid = UUID(admin_id)
    except ValueError:
        raise _not_found() from None
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": TEAM_LOCK})
    row = conn.execute(_FIND, {"id": uid}).mappings().one_or_none()
    if row is None:
        raise _not_found()
    return row


def _is_last_super_admin(conn: Connection, admin: RowMapping) -> bool:
    if admin["role"] != "super_admin" or not admin["approved"] or not admin["active"]:
        return False
    return int(conn.execute(_ACTIVE_SUPER_ADMINS).scalar_one()) <= 1


def _check_change(conn: Connection, me: Actor, admin: RowMapping, loses_super: bool) -> None:
    """In this order: last active super_admin (CONFLICT), yourself (FORBIDDEN), deactivated (CONFLICT)."""
    if loses_super and _is_last_super_admin(conn, admin):
        raise ApiError("CONFLICT", 409, "There must always be at least one super admin.")
    if admin["id"] == me.id:
        raise ApiError("FORBIDDEN", 403, "You cannot change your own role or deactivate yourself.")
    if not admin["active"]:
        raise ApiError("CONFLICT", 409, "This admin is deactivated.")


@router.get("/admin/team")
def list_team(actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return [admin_view(row) for row in conn.execute(_LIST).mappings()]


@router.post("/admin/team/{admin_id}/approve")
def approve_admin(
    admin_id: str, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    admin = _find(conn, admin_id)
    if not admin["active"]:
        raise ApiError("CONFLICT", 409, "This admin is deactivated. Reactivate them first.")
    if admin["approved"]:
        raise ApiError("CONFLICT", 409, "This admin is already approved.")
    licence = read_licence(conn)
    sections = [m for m in MODULES if licence.licensed(m)]
    row = conn.execute(_APPROVE, {"id": admin["id"], "sections": sections}).mappings().one()
    write_audit(conn, actor, "team.approved", row["email"])
    return admin_view(row)


@router.post("/admin/team/{admin_id}/deactivate")
def deactivate_admin(
    admin_id: str, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    admin = _find(conn, admin_id)
    _check_change(conn, actor, admin, loses_super=True)
    row = conn.execute(_SET_ACTIVE, {"id": admin["id"], "active": False}).mappings().one()
    end_admin_sessions(conn, admin["id"])
    write_audit(conn, actor, "team.deactivated" if admin["approved"] else "team.rejected", row["email"])
    return admin_view(row)


@router.post("/admin/team/{admin_id}/reset-password")
def reset_staff_password(
    admin_id: str, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, str]:
    """B15: a Super Admin gives another staff member (any role) a temporary password, shown
    once and stored only as a hash. That person's sessions end at once."""
    admin = _find(conn, admin_id)
    if admin["id"] == actor.id:
        raise ApiError("FORBIDDEN", 403, "Use My account to change your own password.")
    temporary = "".join(secrets.choice(TEMP_ALPHABET) for _ in range(10))
    conn.execute(_SET_PASSWORD, {"id": admin["id"], "password_hash": hash_password(temporary)})
    end_admin_sessions(conn, admin["id"])
    write_audit(conn, actor, "team.password_reset", admin["email"])
    return {"temporary_password": temporary}


@router.post("/admin/team/{admin_id}/reactivate")
def reactivate_admin(
    admin_id: str, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    admin = _find(conn, admin_id)
    if admin["active"]:
        raise ApiError("CONFLICT", 409, "This admin is already active.")
    row = conn.execute(_SET_ACTIVE, {"id": admin["id"], "active": True}).mappings().one()
    write_audit(conn, actor, "team.reactivated", row["email"])
    return admin_view(row)


@router.put("/admin/team/{admin_id}/role")
async def set_role(
    admin_id: str, request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(RoleIn, await request.body())
    if body.role not in ADMIN_ROLES:
        raise ApiError("VALIDATION", 422, "Please choose a role.")
    admin = _find(conn, admin_id)
    _check_change(conn, actor, admin, loses_super=body.role != "super_admin")
    sections = [] if body.role == "finance" else list(admin["sections"])
    row = conn.execute(_SET_ROLE, {"id": admin["id"], "role": body.role, "sections": sections}).mappings().one()
    write_audit(conn, actor, "team.role", f"{row['email']} -> {body.role}")
    return admin_view(row)


@router.put("/admin/team/{admin_id}/sections")
async def set_sections(
    admin_id: str, request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(SectionsIn, await request.body())
    if any(m not in MODULES for m in body.sections):
        raise ApiError("VALIDATION", 422, "Please choose valid sections.")
    admin = _find(conn, admin_id)
    sections = [m for m in MODULES if m in body.sections]
    row = conn.execute(_SET_SECTIONS, {"id": admin["id"], "sections": sections}).mappings().one()
    write_audit(conn, actor, "team.sections", f"{row['email']} -> {', '.join(sections) or 'none'}")
    return admin_view(row)


_STAFF = text(
    "SELECT id, name, role, sections FROM admin_users WHERE approved AND active AND role <> 'finance' "
    "ORDER BY name, id"
)


@router.get("/admin/staff")
def list_staff(actor: Actor = Depends(require_admin), conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    """Who can be chosen in "Assigned to" (cases, enquiries): approved, active, not finance.
    Names and sections only. Admins and the super admin; finance does not assign work."""
    if actor.role == "finance":
        raise ApiError("FORBIDDEN", 403, "Finance does not assign work.")
    return [
        {"id": str(r.id), "name": r.name, "role": r.role, "sections": [m for m in MODULES if m in r.sections]}
        for r in conn.execute(_STAFF)
    ]
