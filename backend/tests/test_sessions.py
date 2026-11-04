"""b29 (only token hashes stored, nothing secret returned) and b30 (session lifetimes)."""

import hashlib
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import PASSWORD, license_modules, signup_applicant

SECRET_WORDS = ("password_hash", "code_hash", "token_hash", "token")


def _cookie_value(response: Any, name: str) -> str:
    header = response.headers.get("set-cookie", "")
    start = header.index(f"{name}=") + len(name) + 1
    return str(header[start:header.index(";", start)])


# ---------- b29 ----------


def test_only_token_hashes_are_stored_and_nothing_secret_returned(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    responses = [
        client.post(
            "/api/auth/super/signup", json={"name": "First Admin", "email": "first@example.test", "password": PASSWORD}
        )
    ]
    admin_token = _cookie_value(responses[0], "mw_admin")
    responses.append(signup_applicant(client, "study", "hash@example.test"))
    applicant_token = _cookie_value(responses[-1], "mw_app_study")
    responses.append(client.get("/api/auth/session"))
    responses.append(client.get("/api/admin/team"))

    stored = {bytes(h) for h in conn.execute(text("SELECT token_hash FROM sessions")).scalars()}
    assert hashlib.sha256(admin_token.encode()).digest() in stored
    assert hashlib.sha256(applicant_token.encode()).digest() in stored
    rows = conn.execute(text("SELECT row_to_json(s)::text FROM sessions s")).scalars().all()
    session_ids = [str(i) for i in conn.execute(text("SELECT id FROM sessions")).scalars()]
    for row in rows:
        assert admin_token not in row and applicant_token not in row

    for response in responses:
        assert response.status_code == 200
        body = response.text
        assert all(word not in body for word in SECRET_WORDS)
        assert admin_token not in body and applicant_token not in body
        assert all(session_id not in body for session_id in session_ids)


# ---------- b30 ----------


def _admin_session(client: TestClient) -> None:
    response = client.post(
        "/api/auth/super/signup", json={"name": "First Admin", "email": "first@example.test", "password": PASSWORD}
    )
    assert response.status_code == 200


def test_admin_idle_for_more_than_8_hours_is_refused(client: TestClient, conn: Connection) -> None:
    _admin_session(client)
    conn.execute(text("UPDATE sessions SET last_seen_at = now() - interval '7 hours 59 minutes'"))
    assert client.get("/api/admin/team").status_code == 200

    conn.execute(text("UPDATE sessions SET last_seen_at = now() - interval '8 hours 1 minute'"))
    refused = client.get("/api/admin/team")
    assert refused.status_code == 401
    assert "mw_admin=" in refused.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["admin"] is None


def test_admin_session_ends_after_7_days(client: TestClient, conn: Connection) -> None:
    _admin_session(client)
    conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    assert client.get("/api/admin/team").status_code == 401


def test_session_lifetimes(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    _admin_session(client)
    signup_applicant(client, "study", "life@example.test")
    lifetimes = dict(
        conn.execute(text("SELECT kind, expires_at - created_at FROM sessions")).tuples().all()
    )
    assert lifetimes["admin"].days == 7
    assert lifetimes["applicant"].days == 30

    conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE kind = 'applicant'"))
    assert client.get("/api/auth/session").json()["applicants"] == {}
