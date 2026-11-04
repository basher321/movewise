"""g03 / b120: setup-status and the setup code, which since B14 protects the Super Admin sign-up."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import get_settings
from auth_helpers import PASSWORD
from conftest import new_client

SETUP_TOKEN = "test-setup-token"


def _signup(client: TestClient, email: str, token: str | None = None) -> Any:
    body: dict[str, str] = {"name": "Admin", "email": email, "password": PASSWORD}
    if token is not None:
        body["setup_token"] = token
    return client.post("/api/auth/super/signup", json=body)


def _admins(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM admin_users")).scalar_one())


@pytest.fixture
def prod_client(api: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "setup_token", SETUP_TOKEN)
    yield new_client(api)


def test_setup_flow_in_production(prod_client: TestClient, conn: Connection) -> None:
    assert _admins(conn) == 0
    assert prod_client.get("/api/auth/setup-status").json() == {"needs_setup": True, "super_admin_exists": False}

    for token in (None, "", "wrong-token"):
        refused = _signup(prod_client, "first@example.test", token)
        assert refused.status_code == 403
        assert refused.json() == {"code": "FORBIDDEN", "message": "The setup code is wrong."}
    assert _admins(conn) == 0

    first = _signup(prod_client, "first@example.test", SETUP_TOKEN)
    assert first.status_code == 200
    assert first.json()["role"] == "super_admin"
    assert prod_client.get("/api/auth/setup-status").json() == {"needs_setup": False, "super_admin_exists": True}

    # Once the Super Admin exists, another Super Admin sign-up is refused, code or not.
    again = _signup(prod_client, "second@example.test", SETUP_TOKEN)
    assert again.status_code == 409
    assert again.json()["code"] == "CONFLICT"


def test_staff_sign_up_needs_no_setup_code_in_production(prod_client: TestClient, conn: Connection) -> None:
    assert _admins(conn) == 0
    staff = prod_client.post(
        "/api/auth/admin/signup", json={"name": "Staff", "email": "staff@example.test", "password": PASSWORD}
    )
    assert staff.status_code == 200
    assert (staff.json()["role"], staff.json()["approved"]) == ("admin", False)
    # A staff account is not a Super Admin, so setup is still needed.
    assert prod_client.get("/api/auth/setup-status").json() == {"needs_setup": True, "super_admin_exists": False}


def test_ten_wrong_codes_from_one_ip_block_the_eleventh(prod_client: TestClient) -> None:
    for i in range(10):
        assert _signup(prod_client, f"try{i}@example.test", "wrong").status_code == 403
    blocked = _signup(prod_client, "first@example.test", SETUP_TOKEN)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_TRIES"


def test_wrong_codes_are_saved_as_failures(prod_client: TestClient, conn: Connection) -> None:
    _signup(prod_client, "first@example.test", "wrong")
    count = conn.execute(
        text("SELECT count(*) FROM signin_failures WHERE kind = 'admin' AND email = 'first@example.test'")
    ).scalar_one()
    assert count == 1


def test_development_needs_no_setup_code(client: TestClient, conn: Connection) -> None:
    assert get_settings().app_env == "development"
    assert _admins(conn) == 0
    assert client.get("/api/auth/setup-status").json() == {"needs_setup": False, "super_admin_exists": False}
    first = _signup(client, "first@example.test")
    assert first.status_code == 200
    assert first.json()["role"] == "super_admin"
