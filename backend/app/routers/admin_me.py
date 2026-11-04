"""B13: the signed-in staff member's own name, email and password (super admin, admin, finance)."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from app.audit import write_audit
from app.auth.accounts import ADMIN_COLUMNS, admin_view, is_unique_violation
from app.auth.deps import admin_actor, current_admin_row
from app.auth.inputs import check_email, check_name, check_password, clean_email
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import end_admin_sessions
from app.db.engine import get_conn
from app.errors import ApiError, parse_body

router = APIRouter()

_SELECT_PASSWORD = text("SELECT password_hash FROM admin_users WHERE id = :id")
_UPDATE_ACCOUNT = text(
    f"UPDATE admin_users SET name = :name, email = :email WHERE id = :id RETURNING {', '.join(ADMIN_COLUMNS)}"
)
_SET_PASSWORD = text("UPDATE admin_users SET password_hash = :password_hash WHERE id = :id")

WRONG_PASSWORD = "Your current password is not right."


class AccountIn(BaseModel):
    name: str
    email: str
    current_password: str = ""


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


def _signed_in_admin(request: Request, conn: Connection) -> RowMapping:
    row = current_admin_row(request, conn)
    if row is None:
        raise ApiError("UNAUTHENTICATED", 401, "Please sign in.")
    return row


def _check_current_password(conn: Connection, admin_id: Any, password: str) -> None:
    stored = conn.execute(_SELECT_PASSWORD, {"id": admin_id}).scalar_one()
    if not verify_password(stored, password):
        raise ApiError("FORBIDDEN", 403, WRONG_PASSWORD)


@router.patch("/auth/admin/me")
async def update_my_account(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    me = _signed_in_admin(request, conn)
    body = parse_body(AccountIn, await request.body())
    name = check_name(body.name)
    email = clean_email(body.email)
    check_email(email)

    changes = []
    if name != me["name"]:
        changes.append(f"name: {me['name']} -> {name}")
    if email != clean_email(me["email"]):
        _check_current_password(conn, me["id"], body.current_password)
        changes.append(f"email: {me['email']} -> {email}")
    if not changes:
        return admin_view(me)

    try:
        with conn.begin_nested():
            row = conn.execute(_UPDATE_ACCOUNT, {"id": me["id"], "name": name, "email": email}).mappings().one()
    except IntegrityError as exc:
        if is_unique_violation(exc, "admin_users_email_key"):
            raise ApiError("CONFLICT", 409, "This email is already used by another staff account.") from None
        raise
    write_audit(conn, admin_actor(row, request), "admin.account_updated", "; ".join(changes))
    return admin_view(row)


@router.post("/auth/admin/password")
async def change_my_password(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, bool]:
    me = _signed_in_admin(request, conn)
    body = parse_body(PasswordIn, await request.body())
    check_password(body.new_password, "New password")
    _check_current_password(conn, me["id"], body.current_password)

    conn.execute(_SET_PASSWORD, {"id": me["id"], "password_hash": hash_password(body.new_password)})
    end_admin_sessions(conn, me["id"], keep=bytes(me["token_hash"]))
    write_audit(conn, admin_actor(me, request), "admin.password_changed", me["email"])
    return {"ok": True}
