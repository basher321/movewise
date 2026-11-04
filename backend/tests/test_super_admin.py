"""b116-b119, b121: the separate Super Admin sign-up and sign-in (B14).
b120 is in test_setup_code.py, b122 in test_auth_admin.py."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import ConfigError
from app.production import check_production
from auth_helpers import PASSWORD, TEST_ADMIN_PASSWORD
from conftest import insert_admin, new_client


def _super_signup(client: TestClient, email: str, name: str = "Owner") -> Any:
    return client.post("/api/auth/super/signup", json={"name": name, "email": email, "password": PASSWORD})


def _super_signin(client: TestClient, email: str, password: str) -> Any:
    return client.post("/api/auth/super/signin", json={"email": email, "password": password})


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar_one())


# ---------- b116 ----------


def test_super_admin_sign_up_once(client: TestClient, conn: Connection, api: FastAPI) -> None:
    first = _super_signup(client, "owner@example.test")
    assert first.status_code == 200
    body = first.json()
    assert (body["role"], body["approved"], body["active"]) == ("super_admin", True, True)
    assert "mw_admin=" in first.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["admin"]["role"] == "super_admin"
    assert _count(conn, "SELECT count(*) FROM audit_log WHERE action = 'admin.signed_up'") == 1

    other = new_client(api)
    again = _super_signup(other, "second-owner@example.test")
    assert again.status_code == 409
    assert again.json() == {"code": "CONFLICT", "message": "A Super Admin already exists. Please sign in."}
    assert "set-cookie" not in again.headers
    assert _count(conn, "SELECT count(*) FROM admin_users") == 1


def test_super_admin_sign_up_input_is_checked(client: TestClient) -> None:
    assert client.post(
        "/api/auth/super/signup", json={"name": "Owner", "email": "o@example.test", "password": "12345"}
    ).status_code == 422
    assert _super_signup(client, "not-an-email").status_code == 422
    assert _super_signup(client, "o@example.test", name=" ").status_code == 422


def test_super_admin_sign_up_with_a_staff_email_is_conflict(client: TestClient, conn: Connection) -> None:
    _, email = insert_admin(conn, "admin")
    response = _super_signup(client, email.upper())
    assert response.status_code == 409


# ---------- b117 ----------


def test_staff_sign_up_never_makes_a_super_admin(client: TestClient, conn: Connection) -> None:
    assert _count(conn, "SELECT count(*) FROM admin_users") == 0
    response = client.post(
        "/api/auth/admin/signup",
        json={"name": "Staff", "email": "staff@example.test", "password": PASSWORD, "setup_token": "ignored"},
    )
    assert response.status_code == 200
    assert (response.json()["role"], response.json()["approved"]) == ("admin", False)
    assert "set-cookie" not in response.headers
    assert _count(conn, "SELECT count(*) FROM admin_users WHERE role = 'super_admin'") == 0


# ---------- b118 ----------


@pytest.mark.parametrize("role", ["admin", "finance"])
def test_staff_cannot_use_the_super_admin_sign_in(client: TestClient, conn: Connection, role: str) -> None:
    _, email = insert_admin(conn, role)
    refused = _super_signin(client, email, TEST_ADMIN_PASSWORD)
    assert refused.status_code == 401
    assert refused.json() == {"code": "UNAUTHENTICATED", "message": "Wrong email or password."}
    assert "set-cookie" not in refused.headers
    failures = "SELECT count(*) FROM signin_failures WHERE kind = 'admin' AND email = :email"
    assert conn.execute(text(failures), {"email": email}).scalar_one() == 1
    # The staff page still works for them.
    assert client.post("/api/auth/admin/signin", json={"email": email, "password": TEST_ADMIN_PASSWORD}).status_code == 200


def test_super_admin_sign_in(client: TestClient, conn: Connection) -> None:
    _, email = insert_admin(conn, "super_admin")
    wrong = _super_signin(client, email, "not the password")
    assert wrong.status_code == 401
    assert wrong.json() == {"code": "UNAUTHENTICATED", "message": "Wrong email or password."}
    right = _super_signin(client, f" {email.upper()} ", TEST_ADMIN_PASSWORD)
    assert right.status_code == 200
    assert right.json()["role"] == "super_admin"
    assert "mw_admin=" in right.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["admin"]["email"] == email
    assert _count(conn, "SELECT count(*) FROM audit_log WHERE action = 'admin.signed_in'") == 1


def test_deactivated_super_admin_cannot_sign_in(client: TestClient, conn: Connection) -> None:
    admin_id, email = insert_admin(conn, "super_admin")
    conn.execute(text("UPDATE admin_users SET active = false WHERE id = :id"), {"id": admin_id})
    response = _super_signin(client, email, TEST_ADMIN_PASSWORD)
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "message": "This account is deactivated."}


# ---------- b119 ----------


def test_setup_status_shows_whether_a_super_admin_exists(client: TestClient, conn: Connection) -> None:
    insert_admin(conn, "admin")
    assert client.get("/api/auth/setup-status").json() == {"needs_setup": False, "super_admin_exists": False}
    _super_signup(client, "owner@example.test")
    assert client.get("/api/auth/setup-status").json() == {"needs_setup": False, "super_admin_exists": True}


def test_a_deactivated_super_admin_does_not_count(client: TestClient, conn: Connection) -> None:
    admin_id, _ = insert_admin(conn, "super_admin")
    conn.execute(text("UPDATE admin_users SET active = false WHERE id = :id"), {"id": admin_id})
    assert client.get("/api/auth/setup-status").json()["super_admin_exists"] is False
    assert _super_signup(client, "owner@example.test").status_code == 200


# ---------- b121 ----------


def test_production_needs_setup_token_while_no_super_admin(conn: Connection) -> None:
    from test_production import _settings

    insert_admin(conn, "admin")
    insert_admin(conn, "finance")
    with pytest.raises(ConfigError, match="SETUP_TOKEN must be set in production while no Super Admin exists."):
        check_production(_settings(setup_token=""), conn)


# ---------- B14 addendum: several Super Admins ----------


def test_a_promoted_admin_is_a_second_super_admin(client: TestClient, conn: Connection, api: FastAPI) -> None:
    from auth_helpers import sign_in_admin_on

    sign_in_admin_on(client, conn, "super_admin")
    staff_id, staff_email = insert_admin(conn, "admin")
    promoted = client.put(f"/api/admin/team/{staff_id}/role", json={"role": "super_admin"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "super_admin"

    other = new_client(api)
    assert _super_signin(other, staff_email, TEST_ADMIN_PASSWORD).status_code == 200
    assert other.get("/api/admin/team").status_code == 200
    # With two Super Admins, one can be changed back to Admin.
    assert client.put(f"/api/admin/team/{staff_id}/role", json={"role": "admin"}).status_code == 200
