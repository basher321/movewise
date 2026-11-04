"""b19, b20: admin sign-up and sign-in (b19/b20 updated for B14: staff sign-up never makes a super admin)."""

import threading
import time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from app.auth.accounts import create_super_admin
from auth_helpers import PASSWORD, TEST_ADMIN_PASSWORD
from conftest import insert_admin


def _signup(client: TestClient, name: str, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/auth/admin/signup", json={"name": name, "email": email, "password": password})


def _signin(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/auth/admin/signin", json={"email": email, "password": password})


# ---------- b19 ----------


def test_staff_sign_ups_wait_for_the_super_admin(client: TestClient) -> None:
    first = client.post(
        "/api/auth/super/signup", json={"name": "First Admin", "email": "first@example.test", "password": PASSWORD}
    )
    assert first.status_code == 200
    body = first.json()
    assert (body["role"], body["approved"], body["active"]) == ("super_admin", True, True)
    assert "mw_admin=" in first.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["admin"]["email"] == "first@example.test"

    second = _signup(client, "Second Admin", "second@example.test")
    assert second.status_code == 200
    pending = second.json()
    assert (pending["role"], pending["approved"]) == ("admin", False)
    assert "set-cookie" not in second.headers

    refused = _signin(client, "second@example.test")
    assert refused.status_code == 403
    assert refused.json() == {"code": "FORBIDDEN", "message": "Your account is waiting for approval."}

    assert client.post(f"/api/admin/team/{pending['id']}/approve").status_code == 200
    allowed = _signin(client, "second@example.test")
    assert allowed.status_code == 200
    assert "mw_admin=" in allowed.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["admin"]["email"] == "second@example.test"


def test_wrong_email_or_password(client: TestClient, conn: Connection) -> None:
    _, email = insert_admin(conn, "admin")
    for attempt in (_signin(client, email, "not the password"), _signin(client, "nobody@example.test")):
        assert attempt.status_code == 401
        assert attempt.json() == {"code": "UNAUTHENTICATED", "message": "Wrong email or password."}
    assert _signin(client, f"  {email.upper()} ", TEST_ADMIN_PASSWORD).status_code == 200


def test_deactivated_admin_cannot_sign_in(client: TestClient, conn: Connection) -> None:
    admin_id, email = insert_admin(conn, "admin")
    conn.execute(text("UPDATE admin_users SET active = false WHERE id = :id"), {"id": admin_id})
    response = _signin(client, email, TEST_ADMIN_PASSWORD)
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "message": "This account is deactivated."}


def test_same_admin_email_twice_is_conflict(client: TestClient) -> None:
    assert _signup(client, "One", "same@example.test").status_code == 200
    again = _signup(client, "Two", " SAME@example.test ")
    assert again.status_code == 409
    assert again.json()["code"] == "CONFLICT"


def test_sign_up_input_is_checked(client: TestClient) -> None:
    assert _signup(client, "Short", "short@example.test", "12345").status_code == 422
    assert _signup(client, "Long", "long@example.test", "x" * 129).status_code == 422
    assert _signup(client, " ", "blank@example.test").status_code == 422
    assert _signup(client, "Bad", "not-an-email").status_code == 422


# ---------- b20 ----------


def test_parallel_super_admin_sign_ups_cannot_both_succeed(test_engine: Engine, conn: Connection) -> None:
    """The second Super Admin sign-up waits on the lock until the first transaction ends.

    Nothing is committed: both transactions are rolled back at the end."""
    conn_a = test_engine.connect()
    conn_b = test_engine.connect()
    trans_a = conn_a.begin()
    trans_b = conn_b.begin()
    result: dict[str, Any] = {}
    try:
        row_a = create_super_admin(conn_a, "Admin A", "a@example.test", "hash")
        assert row_a["role"] == "super_admin"
        pid_b = conn_b.execute(text("SELECT pg_backend_pid()")).scalar_one()

        def sign_up_b() -> None:
            result["b"] = create_super_admin(conn_b, "Admin B", "b@example.test", "hash")

        thread = threading.Thread(target=sign_up_b)
        thread.start()
        wait_event = None
        for _ in range(200):
            conn.execute(text("SELECT pg_stat_clear_snapshot()"))
            wait_event = conn.execute(
                text("SELECT wait_event FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid_b}
            ).scalar_one_or_none()
            if wait_event == "advisory":
                break
            time.sleep(0.05)
        assert wait_event == "advisory"
        assert "b" not in result

        trans_a.rollback()
        thread.join(timeout=10)
        assert not thread.is_alive()
        # A was rolled back, so B is now the only Super Admin.
        assert result["b"]["role"] == "super_admin"
    finally:
        if trans_a.is_active:
            trans_a.rollback()
        if trans_b.is_active:
            trans_b.rollback()
        conn_a.close()
        conn_b.close()
