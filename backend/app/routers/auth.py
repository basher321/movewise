"""Sign-up, sign-in, sign-out and the session.

Bodies are read inside each endpoint, after the module licence check, so the order is
always: module licensed -> input valid -> do the work. A failed sign-in must be kept for the
rate limit: it is saved first and then answered (not raised), so the transaction still commits.
"""

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.audit import Actor, write_audit
from app.auth.accounts import (
    ADMIN_COLUMNS,
    FIRST_ADMIN_LOCK,
    admin_view,
    applicant_view,
    create_admin,
    create_applicant,
    create_super_admin,
    find_admin_for_signin,
    find_applicant,
    super_admin_exists,
)
from app.auth.cookies import ADMIN_COOKIE, applicant_cookie, clear_later, set_session_cookie
from app.auth.deps import (
    admin_actor,
    client_ip,
    current_admin_row,
    current_applicant_row,
    ensure_licensed,
    user_agent,
)
from app.auth.inputs import (
    check_email,
    check_name,
    check_password,
    check_username,
    clean_email,
    optional_email,
    optional_phone,
)
from app.auth.passwords import hash_password, verify_password
from app.auth.ratelimit import is_blocked, is_ip_blocked, record_failure, too_many_tries
from app.auth.sessions import (
    ADMIN_MAX,
    APPLICANT_MAX,
    create_admin_session,
    create_applicant_session,
    end_session,
)
from app.config import get_settings
from app.db.engine import get_conn
from app.errors import ApiError, error_response, parse_body
from app.licence import MODULES, Module

router = APIRouter()

WRONG_SIGNIN = "Wrong username or password."
# Staff still sign in with their email.
WRONG_ADMIN_SIGNIN = "Wrong email or password."
WRONG_SETUP_CODE = "The setup code is wrong."
SETUP_MAX_PER_IP = 10

_SET_LAST_LOGIN = text(
    f"UPDATE admin_users SET last_login_at = now() WHERE id = :id RETURNING {', '.join(ADMIN_COLUMNS)}"
)


class SignUpIn(BaseModel):
    name: str
    username: str
    password: str
    email: str = ""
    phone: str = ""


class AdminSignUpIn(BaseModel):
    name: str
    email: str
    password: str
    # Production only: the Super Admin sign-up must bring SETUP_TOKEN while no Super Admin
    # exists (B14). Ignored on the staff sign-up.
    setup_token: str = ""


class SignInIn(BaseModel):
    email: str
    password: str


class ApplicantSignInIn(BaseModel):
    # The username, or the email for accounts made before usernames.
    login: str
    password: str


class SignOutIn(BaseModel):
    target: Literal["admin", "course", "study", "job", "visa", "all"]


def _valid_email(raw: str) -> str:
    email = clean_email(raw)
    check_email(email)
    return email


def _applicant_actor(row: Any, request: Request) -> Actor:
    return Actor(id=row["id"], name=row["name"], role="applicant", ip=client_ip(request))


def _sign_in_applicant(request: Request, response: Response, conn: Connection, row: Any) -> None:
    token = create_applicant_session(conn, row["id"], row["module"], client_ip(request), user_agent(request))
    set_session_cookie(
        request, response, applicant_cookie(row["module"]), token, int(APPLICANT_MAX.total_seconds())
    )


# ---------- Admins ----------


def _needs_setup(conn: Connection) -> bool:
    """Production only: true while no active Super Admin exists (the Super Admin sign-up needs
    SETUP_TOKEN)."""
    return get_settings().app_env == "production" and not super_admin_exists(conn)


def _setup_refusal(conn: Connection, request: Request, email: str, token: str) -> Response | None:
    """None when the Super Admin sign-up may go on. A wrong setup code is saved as a failed
    admin sign-in from this IP, then answered (not raised) so the failure is committed."""
    # The same lock create_super_admin takes, so two sign-ups cannot both pass this check.
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_ADMIN_LOCK})
    if not _needs_setup(conn):
        return None
    ip = client_ip(request)
    if is_ip_blocked(conn, "admin", ip, SETUP_MAX_PER_IP):
        raise too_many_tries()
    expected = get_settings().setup_token
    if not expected or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        record_failure(conn, email, "admin", ip)
        return error_response("FORBIDDEN", WRONG_SETUP_CODE)
    return None


@router.get("/auth/setup-status")
def setup_status(conn: Connection = Depends(get_conn)) -> dict[str, bool]:
    return {"needs_setup": _needs_setup(conn), "super_admin_exists": super_admin_exists(conn)}


@router.post("/auth/admin/signup", response_model=None)
async def admin_signup(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    """Staff sign-up (B14): always an admin waiting for the Super Admin's approval."""
    body = parse_body(AdminSignUpIn, await request.body())
    name = check_name(body.name)
    email = _valid_email(body.email)
    check_password(body.password)

    row = create_admin(conn, name, body.email.strip(), hash_password(body.password))
    write_audit(conn, admin_actor(row, request), "admin.signed_up", email + " (waiting for approval)")
    return admin_view(row)


@router.post("/auth/super/signup", response_model=None)
async def super_admin_signup(
    request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> dict[str, Any] | Response:
    """First-time setup (B14): makes the Super Admin while none exists, and signs them in."""
    body = parse_body(AdminSignUpIn, await request.body())
    name = check_name(body.name)
    email = _valid_email(body.email)
    check_password(body.password)
    refusal = _setup_refusal(conn, request, email, body.setup_token)
    if refusal is not None:
        return refusal

    row = create_super_admin(conn, name, body.email.strip(), hash_password(body.password))
    write_audit(conn, admin_actor(row, request), "admin.signed_up", email + " (super_admin)")
    token = create_admin_session(conn, row["id"], client_ip(request), user_agent(request))
    set_session_cookie(request, response, ADMIN_COOKIE, token, int(ADMIN_MAX.total_seconds()))
    return admin_view(row)


def _admin_signin(
    request: Request, response: Response, conn: Connection, body: SignInIn, super_only: bool
) -> dict[str, Any] | Response:
    email = _valid_email(body.email)
    ip = client_ip(request)

    if is_blocked(conn, email, "admin", ip):
        raise too_many_tries()
    row = find_admin_for_signin(conn, email)
    right = verify_password(row["password_hash"] if row else None, body.password)
    # On the Super Admin page a staff account is answered like a wrong password.
    if not right or (super_only and row is not None and row["role"] != "super_admin"):
        record_failure(conn, email, "admin", ip)
        return error_response("UNAUTHENTICATED", WRONG_ADMIN_SIGNIN)
    assert row is not None
    if not row["active"]:
        raise ApiError("FORBIDDEN", 403, "This account is deactivated.")
    if not row["approved"]:
        raise ApiError("FORBIDDEN", 403, "Your account is waiting for approval.")

    row = conn.execute(_SET_LAST_LOGIN, {"id": row["id"]}).mappings().one()
    token = create_admin_session(conn, row["id"], ip, user_agent(request))
    set_session_cookie(request, response, ADMIN_COOKIE, token, int(ADMIN_MAX.total_seconds()))
    write_audit(conn, admin_actor(row, request), "admin.signed_in", email)
    return admin_view(row)


@router.post("/auth/admin/signin", response_model=None)
async def admin_signin(
    request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> dict[str, Any] | Response:
    body = parse_body(SignInIn, await request.body())
    return _admin_signin(request, response, conn, body, super_only=False)


@router.post("/auth/super/signin", response_model=None)
async def super_admin_signin(
    request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> dict[str, Any] | Response:
    body = parse_body(SignInIn, await request.body())
    return _admin_signin(request, response, conn, body, super_only=True)


# ---------- Applicants ----------
# Owner decision (2026-11-01): applicants sign up and sign in with a username and password and
# are signed in at once - no email code. Email is optional and not verified. A forgotten password
# is reset by staff (POST /admin/accounts/{id}/reset-password).


@router.post("/auth/applicant/{module}/signup", response_model=None)
async def applicant_signup(
    module: Module, request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    ensure_licensed(conn, module)
    body = parse_body(SignUpIn, await request.body())
    name = check_name(body.name)
    username = check_username(body.username)
    check_password(body.password)
    email = optional_email(body.email)
    phone = optional_phone(body.phone)

    row = create_applicant(conn, module, name, username, email, phone, hash_password(body.password))
    _sign_in_applicant(request, response, conn, row)
    write_audit(conn, _applicant_actor(row, request), "applicant.signed_up", f"{row['public_id']} {username}")
    return applicant_view(row)


@router.post("/auth/applicant/{module}/signin", response_model=None)
async def applicant_signin(
    module: Module, request: Request, response: Response, conn: Connection = Depends(get_conn)
) -> dict[str, Any] | Response:
    ensure_licensed(conn, module)
    body = parse_body(ApplicantSignInIn, await request.body())
    login = body.login.strip().lower()
    if not login or len(login) > 254:
        raise ApiError("VALIDATION", 422, "Please enter your username.")
    ip = client_ip(request)

    if is_blocked(conn, login, module, ip):
        raise too_many_tries()
    row = find_applicant(conn, module, login)
    if not verify_password(row["password_hash"] if row else None, body.password):
        record_failure(conn, login, module, ip)
        return error_response("UNAUTHENTICATED", WRONG_SIGNIN)
    assert row is not None

    _sign_in_applicant(request, response, conn, row)
    return applicant_view(row)


# ---------- Sign-out and session ----------


@router.post("/auth/signout")
async def sign_out(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, bool]:
    body = parse_body(SignOutIn, await request.body())
    if body.target == "all":
        names = [ADMIN_COOKIE] + [applicant_cookie(m) for m in MODULES]
    elif body.target == "admin":
        names = [ADMIN_COOKIE]
    else:
        names = [applicant_cookie(body.target)]
    for name in names:
        token = request.cookies.get(name)
        if token is not None:
            end_session(conn, token)
            clear_later(request, name)
    return {"ok": True}


@router.get("/auth/session")
def get_session(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    admin = current_admin_row(request, conn)
    applicants: dict[str, Any] = {}
    for module in MODULES:
        row = current_applicant_row(request, conn, module)
        if row is not None:
            applicants[module] = applicant_view(row)
    return {"admin": admin_view(admin) if admin else None, "applicants": applicants}
