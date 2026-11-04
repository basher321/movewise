"""Who is calling, and what they may do. All are FastAPI dependencies.

Order of checks: signed in -> module licensed -> role and section.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, Role
from app.auth.cookies import ADMIN_COOKIE, applicant_cookie, clear_later
from app.auth.sessions import read_admin_session, read_applicant_session, token_hash
from app.db.engine import get_conn
from app.errors import ApiError
from app.licence import MODULE_LABELS, MODULES, Module, read_licence


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def ensure_licensed(conn: Connection, module: Module) -> None:
    """Refuse when the module is not in the licence or the licence has expired, for every role."""
    if not read_licence(conn).licensed(module):
        raise ApiError(
            "MODULE_NOT_LICENSED",
            403,
            f"The {MODULE_LABELS[module]} module is not licensed for this installation.",
        )


def _unauthenticated() -> ApiError:
    return ApiError("UNAUTHENTICATED", 401, "Please sign in.")


def admin_actor(row: RowMapping, request: Request) -> Actor:
    return Actor(
        id=row["id"],
        name=row["name"],
        role=cast(Role, row["role"]),
        ip=client_ip(request),
        sections=tuple(m for m in MODULES if m in row["sections"]),
    )


def current_admin_row(request: Request, conn: Connection) -> RowMapping | None:
    """The signed-in admin, or None. A cookie that no longer matches is cleared."""
    token = request.cookies.get(ADMIN_COOKIE)
    if token is None:
        return None
    row = read_admin_session(conn, token)
    if row is None:
        clear_later(request, ADMIN_COOKIE)
    return row


def current_applicant_row(request: Request, conn: Connection, module: Module) -> RowMapping | None:
    name = applicant_cookie(module)
    token = request.cookies.get(name)
    if token is None:
        return None
    row = read_applicant_session(conn, token, module)
    if row is None:
        clear_later(request, name)
    return row


def get_current_actor(request: Request, conn: Connection = Depends(get_conn)) -> Actor:
    """The signed-in admin (any role)."""
    row = current_admin_row(request, conn)
    if row is None:
        raise _unauthenticated()
    return admin_actor(row, request)


def require_admin(actor: Actor = Depends(get_current_actor)) -> Actor:
    return actor


def require_super_admin(actor: Actor = Depends(get_current_actor)) -> Actor:
    if actor.role != "super_admin":
        raise ApiError("FORBIDDEN", 403, "Only the super admin can do this.")
    return actor


def require_finance_or_super(actor: Actor = Depends(get_current_actor)) -> Actor:
    if actor.role not in ("super_admin", "finance"):
        raise ApiError("FORBIDDEN", 403, "Only the super admin or finance can do this.")
    return actor


def ensure_section(conn: Connection, actor: Actor, module: Module) -> None:
    """Module licensed, then super_admin or an admin with this module in their sections. Never finance."""
    ensure_licensed(conn, module)
    if actor.role == "super_admin" or (actor.role == "admin" and module in actor.sections):
        return
    raise ApiError("FORBIDDEN", 403, f"You do not have access to the {MODULE_LABELS[module]} section.")


def require_section(module: Module) -> Callable[..., Actor]:
    """super_admin, or an admin with this module in their sections. Never finance."""

    def check_section(actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)) -> Actor:
        ensure_section(conn, actor, module)
        return actor

    return check_section


def require_module(module: Module) -> Callable[..., None]:
    """Refuse when the module is not in the licence or the licence has expired, for every role."""

    def check_module(conn: Connection = Depends(get_conn)) -> None:
        ensure_licensed(conn, module)

    return check_module


@dataclass(frozen=True)
class Applicant:
    account: RowMapping
    session_hash: bytes
    actor: Actor


def _applicant(request: Request, conn: Connection, module: Module) -> Applicant:
    row = current_applicant_row(request, conn, module)
    if row is None:
        raise _unauthenticated()
    ensure_licensed(conn, module)
    token = request.cookies[applicant_cookie(module)]
    actor = Actor(id=row["id"], name=row["name"], role="applicant", ip=client_ip(request))
    return Applicant(account=row, session_hash=token_hash(token), actor=actor)


def require_applicant(module: Module) -> Callable[..., Applicant]:
    """The applicant signed in to this module."""

    def check_applicant(request: Request, conn: Connection = Depends(get_conn)) -> Applicant:
        return _applicant(request, conn, module)

    return check_applicant


def current_applicant(module: Module, request: Request, conn: Connection = Depends(get_conn)) -> Applicant:
    """require_applicant for routes with the module in the path (/me/{module}/...)."""
    return _applicant(request, conn, module)
