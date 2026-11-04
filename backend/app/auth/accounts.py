"""Admin and applicant account rows, and the AdminUser / ApplicantAccount shapes of F02.

Responses are built only from the columns listed here, so password_hash never leaves.
"""

import secrets
from typing import Any
from uuid import UUID

import psycopg.errors
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.licence import MODULE_LABELS, MODULES, Module

ADMIN_COLUMNS = ("id", "name", "email", "role", "approved", "active", "sections", "created_at")
APPLICANT_COLUMNS = (
    "id", "public_id", "module", "username", "name", "email", "phone", "country", "education",
    "email_verified", "created_at",
)
ID_PREFIX: dict[Module, str] = {"course": "CRS", "study": "STU", "job": "JOB", "visa": "VIS"}
# A-Z and 2-9 without O, I, 0 and 1.
ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ID_ATTEMPTS = 5
# Key of the transaction lock taken while deciding whether a sign-up is the first admin.
FIRST_ADMIN_LOCK = 3_000_001

_ADMIN_SELECT = ", ".join(ADMIN_COLUMNS)
_APPLICANT_SELECT = ", ".join(APPLICANT_COLUMNS)

_INSERT_ADMIN = text(
    "INSERT INTO admin_users (name, email, password_hash, role, approved, active, sections) "
    "VALUES (:name, :email, :password_hash, :role, :approved, true, '{}') "
    f"RETURNING {_ADMIN_SELECT}"
)
_SELECT_ADMIN_FOR_SIGNIN = text(
    f"SELECT {_ADMIN_SELECT}, password_hash FROM admin_users WHERE lower(email) = :email"
)
_INSERT_APPLICANT = text(
    "INSERT INTO applicant_accounts (public_id, module, username, name, email, phone, password_hash) "
    "VALUES (:public_id, :module, :username, :name, :email, :phone, :password_hash) "
    f"RETURNING {_APPLICANT_SELECT}"
)
_SELECT_BY_USERNAME = text(
    f"SELECT {_APPLICANT_SELECT}, password_hash FROM applicant_accounts "
    "WHERE module = :module AND username = :login"
)
_SELECT_BY_EMAIL = text(
    f"SELECT {_APPLICANT_SELECT}, password_hash FROM applicant_accounts "
    "WHERE module = :module AND lower(email) = :login"
)


def admin_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "approved": row["approved"],
        "active": row["active"],
        "sections": [m for m in MODULES if m in row["sections"]],
        "created_at": row["created_at"].isoformat(),
    }


def applicant_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": row["public_id"],
        "module": row["module"],
        "username": row["username"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "country": row["country"],
        "education": row["education"],
        "email_verified": row["email_verified"],
        "created_at": row["created_at"].isoformat(),
    }


def is_unique_violation(exc: IntegrityError, constraint: str) -> bool:
    orig = exc.orig
    return isinstance(orig, psycopg.errors.UniqueViolation) and orig.diag.constraint_name == constraint


_ACTIVE_SUPER_ADMIN_EXISTS = text(
    "SELECT EXISTS (SELECT 1 FROM admin_users WHERE role = 'super_admin' AND active)"
)


def super_admin_exists(conn: Connection) -> bool:
    return bool(conn.execute(_ACTIVE_SUPER_ADMIN_EXISTS).scalar_one())


def _insert_admin(conn: Connection, params: dict[str, Any]) -> RowMapping:
    try:
        with conn.begin_nested():
            return conn.execute(_INSERT_ADMIN, params).mappings().one()
    except IntegrityError as exc:
        if is_unique_violation(exc, "admin_users_email_key"):
            raise ApiError("CONFLICT", 409, "This email already has an admin account. Please sign in.") from None
        raise


def create_admin(conn: Connection, name: str, email: str, password_hash: str) -> RowMapping:
    """A staff sign-up (B14): always an admin waiting for approval, never a super admin."""
    params = {"name": name, "email": email, "password_hash": password_hash, "role": "admin", "approved": False}
    return _insert_admin(conn, params)


def create_super_admin(conn: Connection, name: str, email: str, password_hash: str) -> RowMapping:
    """The Super Admin sign-up (B14): only while no active super admin exists. The lock makes
    two sign-ups at the same moment wait for each other, so only one can succeed."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_ADMIN_LOCK})
    if super_admin_exists(conn):
        raise ApiError("CONFLICT", 409, "A Super Admin already exists. Please sign in.")
    params = {"name": name, "email": email, "password_hash": password_hash, "role": "super_admin", "approved": True}
    return _insert_admin(conn, params)


def find_admin_for_signin(conn: Connection, email: str) -> RowMapping | None:
    return conn.execute(_SELECT_ADMIN_FOR_SIGNIN, {"email": email}).mappings().one_or_none()


def _new_public_id(module: Module) -> str:
    return ID_PREFIX[module] + "-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(6))


def create_applicant(
    conn: Connection,
    module: Module,
    name: str,
    username: str,
    email: str | None,
    phone: str,
    password_hash: str,
) -> RowMapping:
    """The unique indexes decide a taken username or email, so two sign-ups at once give one CONFLICT."""
    for _ in range(ID_ATTEMPTS):
        params = {
            "public_id": _new_public_id(module),
            "module": module,
            "username": username,
            "name": name,
            "email": email,
            "phone": phone,
            "password_hash": password_hash,
        }
        try:
            with conn.begin_nested():
                return conn.execute(_INSERT_APPLICANT, params).mappings().one()
        except IntegrityError as exc:
            if is_unique_violation(exc, "applicant_accounts_module_username_key"):
                raise ApiError("CONFLICT", 409, "This username is taken. Please choose another one.") from None
            if is_unique_violation(exc, "applicant_accounts_module_email_key"):
                raise ApiError(
                    "CONFLICT",
                    409,
                    f"This email already has a {MODULE_LABELS[module]} account. Please sign in.",
                ) from None
            if is_unique_violation(exc, "applicant_accounts_public_id_key"):
                continue
            raise
    raise RuntimeError("could not make a unique applicant id")


def find_applicant(conn: Connection, module: Module, login: str) -> RowMapping | None:
    """By username, or by email when the login has an @ (accounts made before usernames)."""
    sql = _SELECT_BY_EMAIL if "@" in login else _SELECT_BY_USERNAME
    return conn.execute(sql, {"module": module, "login": login}).mappings().one_or_none()


def applicant_by_id(conn: Connection, applicant_id: UUID) -> RowMapping:
    return conn.execute(
        text(f"SELECT {_APPLICANT_SELECT} FROM applicant_accounts WHERE id = :id"), {"id": applicant_id}
    ).mappings().one()
