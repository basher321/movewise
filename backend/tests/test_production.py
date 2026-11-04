"""g01, g02: production start-up checks, docs off, Secure cookies, health without the migration name.

Production clients are made without "with", so the app's start-up check does not run against the
test superuser; g01 calls check_production directly.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import AppSettings, ConfigError, get_settings
from app.production import check_production
from conftest import insert_admin, new_client

GOOD_SECRET = "s" * 32
SETUP_TOKEN = "test-setup-token"


def _settings(**changes: Any) -> AppSettings:
    values: dict[str, Any] = {"app_env": "production", "secret_key": GOOD_SECRET, "setup_token": SETUP_TOKEN}
    values.update(changes)
    return get_settings().model_copy(update=values)


def _is_superuser(conn: Connection) -> bool:
    return bool(conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar_one())


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "setup_token", SETUP_TOKEN)


@pytest.fixture
def prod_client(production: None, api: FastAPI) -> Iterator[TestClient]:
    # production comes first: the app reads APP_ENV when it is made (docs on or off).
    yield new_client(api)


# ---------- g01 ----------


def test_short_secret_key_is_refused(conn: Connection) -> None:
    with pytest.raises(ConfigError, match="SECRET_KEY must have at least 32 characters"):
        check_production(_settings(secret_key="s" * 31), conn)


def test_missing_setup_token_with_no_admin_is_refused(conn: Connection) -> None:
    assert conn.execute(text("SELECT count(*) FROM admin_users")).scalar_one() == 0
    with pytest.raises(ConfigError, match="SETUP_TOKEN must be set"):
        check_production(_settings(setup_token=""), conn)


def test_missing_setup_token_is_fine_once_an_admin_exists(conn: Connection) -> None:
    insert_admin(conn, "super_admin")
    if not _is_superuser(conn):
        check_production(_settings(setup_token=""), conn)
        return
    # The test user is a superuser, so the next check refuses; the token check has passed.
    with pytest.raises(ConfigError, match="superuser"):
        check_production(_settings(setup_token=""), conn)


def test_superuser_database_user_is_refused(conn: Connection) -> None:
    if not _is_superuser(conn):
        pytest.skip("The test database user is not a superuser.")
    with pytest.raises(ConfigError, match="^Database user must not be a superuser in production.$"):
        check_production(_settings(), conn)


def test_limited_role_passes(conn: Connection) -> None:
    exists = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'movewise_app')")).scalar_one()
    if not exists:
        pytest.skip("Role movewise_app does not exist.")
    conn.execute(text("SET LOCAL ROLE movewise_app"))
    check_production(_settings(), conn)


def test_messages_never_contain_values(conn: Connection) -> None:
    secret = "short-secret-value"
    with pytest.raises(ConfigError) as caught:
        check_production(_settings(secret_key=secret), conn)
    assert secret not in str(caught.value)


def test_development_start_up_runs_no_checks(api: FastAPI) -> None:
    assert get_settings().app_env == "development"
    with TestClient(api) as client:
        assert client.get("/api/health").status_code == 200


# ---------- g02 ----------


def test_docs_are_on_in_development(client: TestClient) -> None:
    assert get_settings().app_env == "development"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200, path


def test_docs_are_off_in_production(prod_client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod_client.get(path).status_code == 404, path


def test_cookies_are_secure_in_production(prod_client: TestClient) -> None:
    response = prod_client.post(
        "/api/auth/super/signup",
        json={"name": "First Admin", "email": "first@example.test", "password": "secret12", "setup_token": SETUP_TOKEN},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("mw_admin=")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie


def test_health_hides_the_migration_name_in_production(prod_client: TestClient) -> None:
    response = prod_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
