"""b25 (sign-in rate limit) and b26 (Origin check)."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import TEST_ADMIN_PASSWORD, license_modules, signin_applicant, verified_applicant
from conftest import insert_admin


def _signin(client: TestClient, email: str, password: str) -> Any:
    return client.post("/api/auth/admin/signin", json={"email": email, "password": password})


# ---------- b25 ----------


def test_eleven_failed_sign_ins_give_too_many_tries(client: TestClient, conn: Connection) -> None:
    _, email = insert_admin(conn, "admin")
    for _ in range(10):
        assert _signin(client, email, "wrong password").status_code == 401
    blocked = _signin(client, email, "wrong password")
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_TRIES"
    assert _signin(client, email, TEST_ADMIN_PASSWORD).status_code == 429

    conn.execute(text("UPDATE signin_failures SET at = at - interval '16 minutes'"))
    assert _signin(client, email, TEST_ADMIN_PASSWORD).status_code == 200


def test_limit_is_per_email_and_kind(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    email = "limit@example.test"
    verified_applicant(client, conn, "study", email)
    for _ in range(10):
        assert _signin(client, email, "wrong password").status_code == 401
    assert _signin(client, email, "wrong password").status_code == 429
    assert signin_applicant(client, "study", email).status_code == 200


def test_thirty_failures_from_one_ip(client: TestClient) -> None:
    for number in range(30):
        assert _signin(client, f"user{number}@example.test", "wrong password").status_code == 401
    assert _signin(client, "another@example.test", "wrong password").status_code == 429


def test_failed_sign_ins_are_not_audited(client: TestClient, conn: Connection) -> None:
    before = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
    _signin(client, "nobody@example.test", "wrong password")
    assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == before
    assert conn.execute(text("SELECT count(*) FROM signin_failures WHERE email = 'nobody@example.test'")).scalar_one() == 1


# ---------- b26 ----------


def test_wrong_or_missing_origin_is_forbidden(api: FastAPI, client: TestClient) -> None:
    wrong = client.post("/api/auth/signout", json={"target": "all"}, headers={"Origin": "http://other.invalid"})
    assert wrong.status_code == 403
    assert wrong.json() == {"code": "FORBIDDEN", "message": "Origin not allowed."}

    with TestClient(api, raise_server_exceptions=False) as bare:
        missing = bare.post("/api/auth/signout", json={"target": "all"})
        assert missing.status_code == 403
        assert missing.json()["code"] == "FORBIDDEN"
        assert bare.get("/api/auth/session").status_code == 200

    assert client.post("/api/auth/signout", json={"target": "all"}).status_code == 200
