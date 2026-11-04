"""b31: every successful change in B03 writes exactly one audit row."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection

from auth_helpers import PASSWORD, audit_count, license_modules, signin_applicant, signup_applicant


def _one_row(conn: Connection, action: str, call: Callable[[], Any]) -> Any:
    total, named = audit_count(conn), audit_count(conn, action)
    response = call()
    assert response.status_code == 200, response.text
    assert audit_count(conn) == total + 1, action
    assert audit_count(conn, action) == named + 1, action
    return response


def test_each_change_writes_one_audit_row(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    admin = {"name": "First Admin", "email": "first@example.test", "password": PASSWORD}
    _one_row(conn, "admin.signed_up", lambda: client.post("/api/auth/super/signup", json=admin))
    pending = _one_row(
        conn,
        "admin.signed_up",
        lambda: client.post(
            "/api/auth/admin/signup", json={"name": "Second", "email": "second@example.test", "password": PASSWORD}
        ),
    ).json()
    _one_row(conn, "admin.signed_in", lambda: client.post("/api/auth/admin/signin", json=admin))

    team = f"/api/admin/team/{pending['id']}"
    _one_row(conn, "team.approved", lambda: client.post(f"{team}/approve"))
    _one_row(conn, "team.sections", lambda: client.put(f"{team}/sections", json={"sections": ["study"]}))
    _one_row(conn, "team.role", lambda: client.put(f"{team}/role", json={"role": "finance"}))
    _one_row(conn, "team.deactivated", lambda: client.post(f"{team}/deactivate"))
    _one_row(conn, "team.reactivated", lambda: client.post(f"{team}/reactivate"))

    email = "audit@example.test"
    _one_row(conn, "applicant.signed_up", lambda: signup_applicant(client, "study", email))
    _one_row(
        conn,
        "applicant.profile_updated",
        lambda: client.patch("/api/me/study/profile", json={"name": "Audit Person", "phone": "01712345678"}),
    )
    _one_row(
        conn,
        "applicant.password_changed",
        lambda: client.post("/api/me/study/password", json={"current_password": PASSWORD, "new_password": "newpass1"}),
    )


def test_rejecting_a_pending_admin_is_audited(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    pending = client.post(
        "/api/auth/admin/signup", json={"name": "Pending", "email": "pending@example.test", "password": PASSWORD}
    ).json()
    _one_row(conn, "team.rejected", lambda: client.post(f"/api/admin/team/{pending['id']}/deactivate"))


def test_refused_and_bookkeeping_calls_write_no_audit_row(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    signup_applicant(client, "study", "quiet@example.test")
    before = audit_count(conn)
    signin_applicant(client, "study", "quiet@example.test", "wrong password")
    signin_applicant(client, "study", "quiet@example.test")
    client.post("/api/auth/signout", json={"target": "all"})
    assert audit_count(conn) == before
