"""B15: "Forgot password?" by email link, for staff (any role) and applicants (per module).

The answer to /auth/password/forgot never tells whether an account exists. Only the sha256 of
the link token is stored; the token itself is only in the email."""

import secrets
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.accounts import find_admin_for_signin, find_applicant
from app.auth.deps import client_ip, ensure_licensed
from app.auth.inputs import check_password, clean_email
from app.auth.passwords import hash_password
from app.auth.ratelimit import too_many_tries
from app.auth.sessions import end_admin_sessions, end_applicant_sessions, token_hash
from app.config import get_settings
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import Module
from app.notify.outbox import queue_message
from app.notify.worker import mail_config

router = APIRouter()

Kind = Literal["admin", "course", "study", "job", "visa", "remote"]

LINK_LIFETIME = timedelta(minutes=30)
WINDOW = timedelta(minutes=15)
MAX_PER_ACCOUNT = 3
MAX_PER_IP = 20
RESET_EVENT = "password_reset_link"
NOT_SET_UP = "Email is not set up, so a reset link cannot be sent."
NOT_VALID = "This reset link is not valid."
EXPIRED = "This reset link has expired. Please ask for a new one."

_INSERT = text(
    "INSERT INTO password_resets (kind, admin_id, applicant_id, token_hash, expires_at, ip) "
    "VALUES (:kind, :admin_id, :applicant_id, :token_hash, now() + :lifetime, :ip)"
)
_COUNT_ACCOUNT = text(
    "SELECT count(*) FROM password_resets WHERE created_at > now() - :window "
    "AND (admin_id = :admin_id OR applicant_id = :applicant_id)"
)
_COUNT_IP = text("SELECT count(*) FROM password_resets WHERE created_at > now() - :window AND ip = CAST(:ip AS text)")
_FIND = text(
    "SELECT id, kind, admin_id, applicant_id, used_at IS NOT NULL OR expires_at <= now() AS spent "
    "FROM password_resets WHERE token_hash = :token_hash FOR UPDATE"
)
_USE_ALL = text(
    "UPDATE password_resets SET used_at = now() WHERE used_at IS NULL "
    "AND (admin_id = :admin_id OR applicant_id = :applicant_id)"
)
_SET_ADMIN_PASSWORD = text("UPDATE admin_users SET password_hash = :h WHERE id = :id RETURNING id, name, email, role")
_SET_APPLICANT_PASSWORD = text(
    "UPDATE applicant_accounts SET password_hash = :h WHERE id = :id RETURNING id, name, public_id"
)


class ForgotIn(BaseModel):
    kind: Kind
    login: str


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.get("/auth/password/options")
def password_options(conn: Connection = Depends(get_conn)) -> dict[str, bool]:
    return {"email": mail_config(conn) is not None}


def _find_account(conn: Connection, kind: Kind, login: str) -> tuple[RowMapping, str] | None:
    """The account and the address to send to, or None (no account, inactive, or no email)."""
    if kind == "admin":
        row = find_admin_for_signin(conn, clean_email(login))
        if row is None or not row["active"] or not row["approved"]:
            return None
        return row, row["email"]
    row = find_applicant(conn, kind, login.strip().lower())
    if row is None or not row["email"]:
        return None
    return row, row["email"]


@router.post("/auth/password/forgot")
async def forgot_password(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, bool]:
    body = parse_body(ForgotIn, await request.body())
    if body.kind != "admin":
        ensure_licensed(conn, body.kind)
    if not body.login.strip() or len(body.login) > 254:
        raise ApiError("VALIDATION", 422, "Please enter your email or username.")
    if mail_config(conn) is None:
        raise ApiError("CONFLICT", 409, NOT_SET_UP)

    found = _find_account(conn, body.kind, body.login)
    if found is None:
        return {"ok": True}
    row, address = found
    ip = client_ip(request)
    if ip is not None and conn.execute(_COUNT_IP, {"window": WINDOW, "ip": ip}).scalar_one() >= MAX_PER_IP:
        raise too_many_tries()
    ids = {"admin_id": row["id"] if body.kind == "admin" else None, "applicant_id": None if body.kind == "admin" else row["id"]}
    if conn.execute(_COUNT_ACCOUNT, {"window": WINDOW, **ids}).scalar_one() >= MAX_PER_ACCOUNT:
        return {"ok": True}

    token = secrets.token_urlsafe(32)
    conn.execute(
        _INSERT,
        {"kind": body.kind, **ids, "token_hash": token_hash(token), "lifetime": LINK_LIFETIME, "ip": ip},
    )
    link = f"{get_settings().site_base}/reset-password?token={token}"
    queue_message(
        conn,
        row["name"],
        address,
        None,
        None if body.kind == "admin" else body.kind,
        RESET_EVENT,
        "Reset your password",
        f"Hello {row['name']},\n\nWe got a request to reset your password. Open this link to choose a new "
        f"one. It works once, for 30 minutes:\n\n{link}\n\nIf you did not ask for this, you can ignore this email; "
        "your password stays the same.",
    )
    role: Any = row["role"] if body.kind == "admin" else "applicant"
    who = row["email"] if body.kind == "admin" else row["public_id"]
    write_audit(conn, Actor(id=row["id"], name=row["name"], role=role, ip=ip), "password.reset_requested", who)
    return {"ok": True}


@router.post("/auth/password/reset")
async def reset_password(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    body = parse_body(ResetIn, await request.body())
    token = body.token.strip()
    if not token or len(token) > 200:
        raise ApiError("VALIDATION", 422, NOT_VALID)
    link = conn.execute(_FIND, {"token_hash": token_hash(token)}).mappings().one_or_none()
    if link is None:
        raise ApiError("VALIDATION", 422, NOT_VALID)
    if link["spent"]:
        raise ApiError("EXPIRED", 410, EXPIRED)
    check_password(body.new_password, "New password")

    new_hash = hash_password(body.new_password)
    ip = client_ip(request)
    if link["kind"] == "admin":
        row = conn.execute(_SET_ADMIN_PASSWORD, {"h": new_hash, "id": link["admin_id"]}).mappings().one()
        end_admin_sessions(conn, row["id"])
        actor = Actor(id=row["id"], name=row["name"], role=row["role"], ip=ip)
        who = row["email"]
    else:
        row = conn.execute(_SET_APPLICANT_PASSWORD, {"h": new_hash, "id": link["applicant_id"]}).mappings().one()
        end_applicant_sessions(conn, row["id"])
        actor = Actor(id=row["id"], name=row["name"], role="applicant", ip=ip)
        who = row["public_id"]
    conn.execute(_USE_ALL, {"admin_id": link["admin_id"], "applicant_id": link["applicant_id"]})
    write_audit(conn, actor, "password.reset_by_link", who)
    module: Module | None = None if link["kind"] == "admin" else link["kind"]
    return {"ok": True, "kind": module or "admin"}
