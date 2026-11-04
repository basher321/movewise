"""b109-b115: staff change their own name, email and password (B13)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import TEST_ADMIN_PASSWORD, sign_in_admin_on, sign_in_existing_admin_on
from conftest import insert_admin, new_client

NEW_PASSWORD = "brand new pass"


def _audit(conn: Connection, action: str) -> list[Any]:
    return list(
        conn.execute(
            text("SELECT by_name, action, detail FROM audit_log WHERE action = :action ORDER BY created_at"),
            {"action": action},
        ).mappings()
    )


def _account(client: TestClient, name: str, email: str, current_password: str = "") -> Any:
    return client.patch(
        "/api/auth/admin/me", json={"name": name, "email": email, "current_password": current_password}
    )


def _password(client: TestClient, current: str, new: str) -> Any:
    return client.post("/api/auth/admin/password", json={"current_password": current, "new_password": new})


def _signin(client: TestClient, email: str, password: str) -> Any:
    return client.post("/api/auth/admin/signin", json={"email": email, "password": password})


# ---------- b109 ----------


def test_change_name(client: TestClient, conn: Connection) -> None:
    _, email = sign_in_admin_on(client, conn, "super_admin")
    response = _account(client, "  New Name  ", email)
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert client.get("/api/auth/session").json()["admin"]["name"] == "New Name"
    rows = _audit(conn, "admin.account_updated")
    assert len(rows) == 1 and "name: Test super_admin -> New Name" in rows[0]["detail"]


def test_nothing_changed_writes_no_audit(client: TestClient, conn: Connection) -> None:
    _, email = sign_in_admin_on(client, conn, "admin")
    assert _account(client, "Test admin", email.upper()).status_code == 200
    assert _audit(conn, "admin.account_updated") == []


# ---------- b110 ----------


def test_email_change_needs_current_password(client: TestClient, conn: Connection, api: FastAPI) -> None:
    _, email = sign_in_admin_on(client, conn, "admin")
    wrong = _account(client, "Test admin", "moved@example.test", "not my password")
    assert wrong.status_code == 403
    assert wrong.json() == {"code": "FORBIDDEN", "message": "Your current password is not right."}
    missing = _account(client, "Test admin", "moved@example.test")
    assert missing.status_code == 403
    assert _audit(conn, "admin.account_updated") == []

    right = _account(client, "Test admin", "Moved@Example.test", TEST_ADMIN_PASSWORD)
    assert right.status_code == 200
    assert right.json()["email"] == "moved@example.test"
    assert len(_audit(conn, "admin.account_updated")) == 1

    other = new_client(api)
    assert _signin(other, email, TEST_ADMIN_PASSWORD).status_code == 401
    assert _signin(other, "moved@example.test", TEST_ADMIN_PASSWORD).status_code == 200


# ---------- b111 ----------


def test_email_already_used_is_conflict(client: TestClient, conn: Connection) -> None:
    _, taken = insert_admin(conn, "finance")
    sign_in_admin_on(client, conn, "admin")
    response = _account(client, "Test admin", taken.upper(), TEST_ADMIN_PASSWORD)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


# ---------- b112 ----------


def test_change_password(client: TestClient, conn: Connection, api: FastAPI) -> None:
    admin_id, email = sign_in_admin_on(client, conn, "finance")
    elsewhere = new_client(api)
    sign_in_existing_admin_on(elsewhere, conn, admin_id)
    assert elsewhere.get("/api/auth/session").json()["admin"] is not None

    wrong = _password(client, "not my password", NEW_PASSWORD)
    assert wrong.status_code == 403 and wrong.json()["code"] == "FORBIDDEN"
    assert _audit(conn, "admin.password_changed") == []

    right = _password(client, TEST_ADMIN_PASSWORD, NEW_PASSWORD)
    assert right.status_code == 200 and right.json() == {"ok": True}
    assert client.get("/api/auth/session").json()["admin"]["email"] == email
    assert elsewhere.get("/api/auth/session").json()["admin"] is None

    fresh = new_client(api)
    assert _signin(fresh, email, TEST_ADMIN_PASSWORD).status_code == 401
    assert _signin(fresh, email, NEW_PASSWORD).status_code == 200
    rows = _audit(conn, "admin.password_changed")
    assert len(rows) == 1 and rows[0]["detail"] == email


# ---------- b113 ----------


def test_bad_input_is_validation(client: TestClient, conn: Connection) -> None:
    _, email = sign_in_admin_on(client, conn, "admin")
    assert _password(client, TEST_ADMIN_PASSWORD, "12345").json()["code"] == "VALIDATION"
    assert _account(client, "Test admin", "not-an-email", TEST_ADMIN_PASSWORD).json()["code"] == "VALIDATION"
    assert _account(client, "   ", email).json()["code"] == "VALIDATION"
    assert client.patch("/api/auth/admin/me", content=b"{bad").status_code == 422


# ---------- b114 ----------


def test_needs_admin_session(client: TestClient) -> None:
    patched = _account(client, "X", "x@example.test", "whatever")
    assert patched.status_code == 401 and patched.json()["code"] == "UNAUTHENTICATED"
    posted = _password(client, "whatever", NEW_PASSWORD)
    assert posted.status_code == 401 and posted.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("role", ["super_admin", "admin", "finance"])
def test_every_staff_role_can_change(client: TestClient, conn: Connection, role: str) -> None:
    _, email = sign_in_admin_on(client, conn, role)
    assert _account(client, "Renamed", email).status_code == 200
    assert _password(client, TEST_ADMIN_PASSWORD, NEW_PASSWORD).status_code == 200


# ---------- b115 ----------


def test_no_password_in_responses_or_audit(client: TestClient, conn: Connection) -> None:
    _, email = sign_in_admin_on(client, conn, "super_admin")
    responses = [
        _account(client, "Other Name", "renamed@example.test", TEST_ADMIN_PASSWORD),
        _password(client, TEST_ADMIN_PASSWORD, NEW_PASSWORD),
    ]
    for response in responses:
        assert response.status_code == 200
        body = response.text
        assert "password" not in body and TEST_ADMIN_PASSWORD not in body and NEW_PASSWORD not in body
    details = " ".join(r["detail"] for r in _audit(conn, "admin.account_updated") + _audit(conn, "admin.password_changed"))
    assert TEST_ADMIN_PASSWORD not in details and NEW_PASSWORD not in details
