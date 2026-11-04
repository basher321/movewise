"""Sessions. The cookie holds a random 32-byte token; the database stores only its sha256.

Admin sessions end after 8 hours without activity and after 7 days at most; applicant
sessions after 30 days. An expired session counts as signed out.
"""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.auth.accounts import ADMIN_COLUMNS, APPLICANT_COLUMNS
from app.licence import Module

ADMIN_IDLE = timedelta(hours=8)
ADMIN_MAX = timedelta(days=7)
APPLICANT_MAX = timedelta(days=30)
# last_seen_at is refreshed at most once a minute.
TOUCH_AFTER = timedelta(seconds=60)
MAX_USER_AGENT = 500

_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")

_INSERT = text(
    "INSERT INTO sessions (token_hash, kind, admin_id, applicant_id, module, expires_at, ip, user_agent) "
    "VALUES (:token_hash, :kind, :admin_id, :applicant_id, :module, now() + :lifetime, :ip, :user_agent)"
)
_SELECT_ADMIN = text(
    "SELECT s.token_hash, s.last_seen_at < now() - :touch AS stale, "
    + ", ".join(f"a.{column}" for column in ADMIN_COLUMNS)
    + " FROM sessions s JOIN admin_users a ON a.id = s.admin_id "
    "WHERE s.token_hash = :token_hash AND s.kind = 'admin' "
    "AND s.expires_at > now() AND s.last_seen_at > now() - :idle"
)
_SELECT_APPLICANT = text(
    "SELECT s.token_hash, s.last_seen_at < now() - :touch AS stale, "
    + ", ".join(f"p.{column}" for column in APPLICANT_COLUMNS)
    + " FROM sessions s JOIN applicant_accounts p ON p.id = s.applicant_id "
    "WHERE s.token_hash = :token_hash AND s.kind = 'applicant' AND s.module = :module "
    "AND s.expires_at > now()"
)
_TOUCH = text("UPDATE sessions SET last_seen_at = now() WHERE token_hash = :token_hash")
_DELETE_ONE = text("DELETE FROM sessions WHERE token_hash = :token_hash")
_DELETE_ADMIN = text("DELETE FROM sessions WHERE admin_id = :admin_id")
_DELETE_ADMIN_OTHERS = text("DELETE FROM sessions WHERE admin_id = :admin_id AND token_hash <> :keep")
_DELETE_APPLICANT = text("DELETE FROM sessions WHERE applicant_id = :applicant_id")
_DELETE_APPLICANT_OTHERS = text(
    "DELETE FROM sessions WHERE applicant_id = :applicant_id AND token_hash <> :keep"
)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def _usable(token: str | None) -> bool:
    return token is not None and _TOKEN_RE.fullmatch(token) is not None


def _create(
    conn: Connection,
    kind: str,
    lifetime: timedelta,
    ip: str | None,
    user_agent: str | None,
    admin_id: UUID | None = None,
    applicant_id: UUID | None = None,
    module: Module | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        _INSERT,
        {
            "token_hash": token_hash(token),
            "kind": kind,
            "admin_id": admin_id,
            "applicant_id": applicant_id,
            "module": module,
            "lifetime": lifetime,
            "ip": ip,
            "user_agent": (user_agent or "")[:MAX_USER_AGENT] or None,
        },
    )
    return token


def create_admin_session(conn: Connection, admin_id: UUID, ip: str | None, user_agent: str | None) -> str:
    return _create(conn, "admin", ADMIN_MAX, ip, user_agent, admin_id=admin_id)


def create_applicant_session(
    conn: Connection, applicant_id: UUID, module: Module, ip: str | None, user_agent: str | None
) -> str:
    return _create(conn, "applicant", APPLICANT_MAX, ip, user_agent, applicant_id=applicant_id, module=module)


def _found(conn: Connection, row: RowMapping | None, wanted: bytes) -> bool:
    if row is None or not hmac.compare_digest(bytes(row["token_hash"]), wanted):
        return False
    if row["stale"]:
        conn.execute(_TOUCH, {"token_hash": wanted})
    return True


def read_admin_session(conn: Connection, token: str | None) -> RowMapping | None:
    """The admin of a valid session, or None. A session of an unapproved or deactivated admin is refused."""
    if not _usable(token):
        return None
    assert token is not None
    wanted = token_hash(token)
    row = conn.execute(
        _SELECT_ADMIN, {"token_hash": wanted, "touch": TOUCH_AFTER, "idle": ADMIN_IDLE}
    ).mappings().one_or_none()
    if not _found(conn, row, wanted):
        return None
    assert row is not None
    if not (row["approved"] and row["active"]):
        return None
    return row


def read_applicant_session(conn: Connection, token: str | None, module: Module) -> RowMapping | None:
    if not _usable(token):
        return None
    assert token is not None
    wanted = token_hash(token)
    row = conn.execute(
        _SELECT_APPLICANT, {"token_hash": wanted, "module": module, "touch": TOUCH_AFTER}
    ).mappings().one_or_none()
    return row if _found(conn, row, wanted) else None


def end_session(conn: Connection, token: str | None) -> None:
    if _usable(token):
        assert token is not None
        conn.execute(_DELETE_ONE, {"token_hash": token_hash(token)})


def end_admin_sessions(conn: Connection, admin_id: UUID, keep: bytes | None = None) -> None:
    """Ends every session of the admin, except the one whose hash is keep."""
    if keep is None:
        conn.execute(_DELETE_ADMIN, {"admin_id": admin_id})
    else:
        conn.execute(_DELETE_ADMIN_OTHERS, {"admin_id": admin_id, "keep": keep})


def end_applicant_sessions(conn: Connection, applicant_id: UUID, keep: bytes | None = None) -> None:
    """Ends every session of the account, except the one whose hash is keep."""
    if keep is None:
        conn.execute(_DELETE_APPLICANT, {"applicant_id": applicant_id})
    else:
        conn.execute(_DELETE_APPLICANT_OTHERS, {"applicant_id": applicant_id, "keep": keep})
