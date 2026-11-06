"""Helpers for the B03 tests. All data is made inside the test transaction."""

import re
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.auth.cookies import ADMIN_COOKIE, COOKIE_PATH
from app.auth.sessions import create_admin_session
from conftest import COOKIE_DOMAIN, insert_admin

PASSWORD = "secret12"
TEST_ADMIN_PASSWORD = "test password"


def license_modules(conn: Connection, *modules: str) -> None:
    """Turns the licence on for exactly these modules (test data only)."""
    conn.execute(
        text(
            "UPDATE licence SET key = 'test-licence', holder = 'Test Holder', expires_at = NULL, "
            "module_course = :course, module_study = :study, module_job = :job, module_visa = :visa, module_remote = :remote "
            "WHERE singleton = 'licence'"
        ),
        {m: m in modules for m in ("course", "study", "job", "visa", "remote")},
    )


def sign_in_admin_on(
    client: TestClient, conn: Connection, role: str, sections: list[str] | None = None
) -> tuple[Any, str]:
    """A new approved admin signed in on this client only. Returns (id, email)."""
    admin_id, email = insert_admin(conn, role, sections)
    sign_in_existing_admin_on(client, conn, admin_id)
    return admin_id, email


def sign_in_existing_admin_on(client: TestClient, conn: Connection, admin_id: Any) -> str:
    """A new session for this admin, on this client only. Returns the token."""
    token = create_admin_session(conn, admin_id, "testclient", "pytest")
    client.cookies.set(ADMIN_COOKIE, token, domain=COOKIE_DOMAIN, path=COOKIE_PATH)
    return token


def username_for(email: str) -> str:
    """A valid username made from a test email: its part before @, letters, digits, dots and _."""
    base = re.sub(r"[^a-z0-9._]", "", email.strip().lower().split("@")[0])
    return (base + "user")[:30] if len(base) < 3 else base[:30]


def signup_applicant(
    client: TestClient,
    module: str,
    email: str,
    password: str = PASSWORD,
    name: str = "Test Person",
    username: str | None = None,
) -> Any:
    """Signs up with a username (made from the email unless given) and that email.
    The client is then signed in to that module."""
    body = {"name": name, "username": username or username_for(email), "email": email, "password": password}
    return client.post(f"/api/auth/applicant/{module}/signup", json=body)


def signin_applicant(client: TestClient, module: str, login: str, password: str = PASSWORD) -> Any:
    """login is a username, or an email."""
    return client.post(f"/api/auth/applicant/{module}/signin", json={"login": login, "password": password})


def verified_applicant(client: TestClient, conn: Connection, module: str, email: str) -> dict[str, Any]:
    """Signs up (no email code any more); the client is then signed in to that module."""
    response = signup_applicant(client, module, email)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def audit_count(conn: Connection, action: str | None = None) -> int:
    if action is None:
        return int(conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one())
    return int(
        conn.execute(text("SELECT count(*) FROM audit_log WHERE action = :action"), {"action": action}).scalar_one()
    )
