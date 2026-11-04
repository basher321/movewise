"""Sign-in rate limit: after 10 failed sign-ins for one email and kind in 15 minutes, or 30
from one IP, sign-in answers TOO_MANY_TRIES until the window passes. Refused attempts are not
counted, so the window does not keep moving. Rows are never deleted; old ones are ignored."""

from datetime import timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.errors import ApiError

SignInKind = Literal["admin", "course", "study", "job", "visa"]

WINDOW = timedelta(minutes=15)
MAX_PER_EMAIL = 10
MAX_PER_IP = 30

_COUNT = text(
    "SELECT "
    "count(*) FILTER (WHERE email = :email AND kind = :kind) AS by_email, "
    "count(*) FILTER (WHERE ip = CAST(:ip AS text)) AS by_ip "
    "FROM signin_failures "
    "WHERE at > now() - :window AND ((email = :email AND kind = :kind) OR ip = CAST(:ip AS text))"
)
_INSERT = text("INSERT INTO signin_failures (email, kind, ip) VALUES (:email, :kind, :ip)")
_COUNT_IP = text(
    "SELECT count(*) FROM signin_failures WHERE kind = :kind AND ip = CAST(:ip AS text) AND at > now() - :window"
)


def too_many_tries() -> ApiError:
    return ApiError("TOO_MANY_TRIES", 429, "Too many sign-in attempts. Please try again in 15 minutes.")


def is_blocked(conn: Connection, email: str, kind: SignInKind, ip: str | None) -> bool:
    row = conn.execute(_COUNT, {"email": email, "kind": kind, "ip": ip, "window": WINDOW}).mappings().one()
    return row["by_email"] >= MAX_PER_EMAIL or (ip is not None and row["by_ip"] >= MAX_PER_IP)


def is_ip_blocked(conn: Connection, kind: SignInKind, ip: str | None, limit: int) -> bool:
    """True when this IP has at least limit failures of this kind in the window (setup code: 10)."""
    if ip is None:
        return False
    count = conn.execute(_COUNT_IP, {"kind": kind, "ip": ip, "window": WINDOW}).scalar_one()
    return count >= limit


def record_failure(conn: Connection, email: str, kind: SignInKind, ip: str | None) -> None:
    conn.execute(_INSERT, {"email": email, "kind": kind, "ip": ip})
