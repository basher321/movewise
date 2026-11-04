"""Test fixtures. Run pytest from backend/.

Tests use only TEST_DATABASE_URL. The run refuses to start (pytest_configure) and the
test_url fixture refuses again unless its database name ends with "_test" and it is not
the DATABASE_URL database.

- migrated_db: once per session, applies migrations to the test database.
- conn: per test, a connection inside a transaction that is always rolled back.
- client: the app, with its database dependencies pointed at the test connection. It sends
  Origin: FRONTEND_ORIGIN. Clients made with new_client(api) share the act_as sign-in.
- act_as: signs in a real admin of that role (a real admin_users row and session cookie).
- fast_passwords: argon2 with cheap settings, for every test, so sign-ups stay fast.
- licence_keys: a temporary key pair made for the test; the app checks keys against it.
- settings_body: a valid PUT /api/settings body, with optional changes.
"""

import copy
import os

# The notification worker must never start in tests: it would use DATABASE_URL, not the test
# database. Set before anything reads the settings.
os.environ["NOTIFY_WORKER"] = "off"
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from argon2 import PasswordHasher
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from app import licence
from app.audit import Actor, Role
from app.auth import passwords
from app.auth.cookies import ADMIN_COOKIE, COOKIE_PATH
from app.auth.sessions import create_admin_session
from app.config import BACKEND_DIR, ConfigError, ensure_safe_test_database, get_settings
from app.db.engine import get_conn, get_engine, make_engine
from app.db.migrate import run_migrations

PROJECT_DIR = BACKEND_DIR.parent


def _safe_test_url() -> str:
    try:
        settings = get_settings()
        ensure_safe_test_database(settings.database_url, settings.test_database_url)
    except ConfigError as exc:
        pytest.exit(f"Refusing to run tests: {exc}", returncode=2)
    return settings.test_database_url


def pytest_configure(config: pytest.Config) -> None:
    _safe_test_url()


@pytest.fixture(scope="session")
def test_url() -> str:
    return _safe_test_url()


@pytest.fixture(scope="session")
def migrated_db(test_url: str) -> None:
    run_migrations(test_url, log=lambda _: None)


@pytest.fixture(scope="session")
def test_engine(test_url: str, migrated_db: None) -> Iterator[Engine]:
    engine = make_engine(test_url)
    yield engine
    engine.dispose()


@pytest.fixture
def conn(test_engine: Engine) -> Iterator[Connection]:
    connection = test_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def api(conn: Connection, test_engine: Engine) -> FastAPI:
    from app.main import create_app  # imported here so the safety check above runs first

    application = create_app()

    def use_test_conn() -> Connection:
        return conn

    def use_test_engine() -> Engine:
        return test_engine

    application.dependency_overrides[get_conn] = use_test_conn
    application.dependency_overrides[get_engine] = use_test_engine
    application.state.test_clients = []
    application.state.test_cookies = {}
    return application


# TestClient talks to host "testserver"; cookies set by the app are stored for "testserver.local".
COOKIE_DOMAIN = "testserver.local"


def new_client(api: FastAPI) -> TestClient:
    """A client that sends Origin: FRONTEND_ORIGIN and carries the act_as sign-in."""
    test_client = TestClient(
        api, raise_server_exceptions=False, headers={"Origin": get_settings().frontend_origin}
    )
    for name, value in api.state.test_cookies.items():
        test_client.cookies.set(name, value, domain=COOKIE_DOMAIN, path=COOKIE_PATH)
    api.state.test_clients.append(test_client)
    return test_client


def set_test_cookie(api: FastAPI, name: str, value: str | None) -> None:
    """Sets (or with None removes) a cookie on every client of this test."""
    if value is None:
        api.state.test_cookies.pop(name, None)
    else:
        api.state.test_cookies[name] = value
    for test_client in api.state.test_clients:
        try:
            test_client.cookies.delete(name, domain=COOKIE_DOMAIN, path=COOKIE_PATH)
        except KeyError:
            pass
        if value is not None:
            test_client.cookies.set(name, value, domain=COOKIE_DOMAIN, path=COOKIE_PATH)


@pytest.fixture
def client(api: FastAPI) -> Iterator[TestClient]:
    with new_client(api) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def storage_root_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("storage")
    if _inside_project(path):
        pytest.exit("Refusing to run: pytest's temporary folder is inside the project.", returncode=2)
    return path


@pytest.fixture(autouse=True)
def temp_storage(storage_root_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Uploaded files go to a temporary folder made for the test run, never backend/storage."""
    monkeypatch.setattr(get_settings(), "storage_dir", str(storage_root_dir))
    return storage_root_dir


@pytest.fixture(autouse=True)
def fresh_ai_limits() -> None:
    """B17: the advisor's in-process question counter starts empty for every test."""
    from app.ai import advisor

    advisor.reset_limits()


@pytest.fixture(autouse=True)
def fast_passwords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "_hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))
    monkeypatch.setattr(passwords, "_dummy_hash", None)


_INSERT_TEST_ADMIN = text(
    "INSERT INTO admin_users (name, email, password_hash, role, approved, active, sections) "
    "VALUES (:name, :email, :password_hash, :role, true, true, CAST(:sections AS text[])) RETURNING id"
)


def insert_admin(
    conn: Connection, role: str, sections: list[str] | None = None, name: str | None = None
) -> tuple[Any, str]:
    """An approved, active admin made directly in the test transaction. Returns (id, email)."""
    email = f"test-{role}-{uuid4().hex[:8]}@example.test"
    if sections is None:
        sections = ["course", "study", "job"] if role == "admin" else []
    admin_id = conn.execute(
        _INSERT_TEST_ADMIN,
        {
            "name": name or f"Test {role}",
            "email": email,
            "password_hash": passwords.hash_password("test password"),
            "role": role,
            "sections": sections,
        },
    ).scalar_one()
    return admin_id, email


@pytest.fixture
def act_as(api: FastAPI, conn: Connection) -> Callable[[Role | None], Actor | None]:
    def set_actor(role: Role | None) -> Actor | None:
        if role is None:
            set_test_cookie(api, ADMIN_COOKIE, None)
            return None
        if role == "applicant":
            raise ValueError("act_as signs in admins only")
        admin_id, _ = insert_admin(conn, role)
        token = create_admin_session(conn, admin_id, "testclient", "pytest")
        set_test_cookie(api, ADMIN_COOKIE, token)
        return Actor(id=admin_id, name=f"Test {role}", role=role, ip="testclient")

    return set_actor


@dataclass(frozen=True)
class LicenceKeys:
    private_key: Ed25519PrivateKey
    private_path: Path


def _inside_project(path: Path) -> bool:
    target = os.path.normcase(str(path.resolve()))
    root = os.path.normcase(str(PROJECT_DIR))
    return target == root or target.startswith(root + os.sep)


@pytest.fixture
def licence_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LicenceKeys:
    # The test key pair lives only in pytest's temporary folder, never in the project.
    if _inside_project(tmp_path):
        pytest.exit("Refusing to run: pytest's temporary folder is inside the project.", returncode=2)
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "test_licence_private.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key = private_key.public_key()
    monkeypatch.setattr(licence, "load_public_key", lambda: public_key)
    return LicenceKeys(private_key=private_key, private_path=private_path)


_VALID_SETTINGS: dict[str, Any] = {
    "name": "Test Agency",
    "tagline": "",
    "brand_color": "#4F46E5",
    "hero_title": "",
    "hero_text": "",
    "stats": [{"number": "1", "label": "one"}, {"number": "2", "label": "two"}, {"number": "3", "label": "three"}],
    "about_title": "",
    "about_text": "",
    "address": "",
    "phone": "",
    "email": "",
    "hours": "",
    "facebook": "",
    "website": "",
    "invoice_prefix": "INV",
    "invoice_footer": "",
    "vat_bin": "",
    "default_fee_poisha": {"study": 100000, "job": 100000},
    "gateways": {
        "sslcommerz": {"enabled": False, "sandbox": True, "store_id": "", "store_password": ""},
        "bkash": {
            "enabled": False,
            "sandbox": True,
            "app_key": "",
            "app_secret": "",
            "username": "",
            "password": "",
        },
        "nagad": {"enabled": False, "sandbox": True, "merchant_id": "", "private_key": ""},
        "manual": {"enabled": True, "instructions": ""},
    },
    "mail": {
        "sender_name": "",
        "sender_email": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "",
        "smtp_password": "",
    },
    "whatsapp": {
        "number": "",
        "token": "",
        "phone_number_id": "",
        "template_name": "",
        "template_language": "en",
        "api_version": "v21.0",
    },
}


@pytest.fixture
def settings_body() -> Callable[..., dict[str, Any]]:
    def make(**changes: Any) -> dict[str, Any]:
        body = copy.deepcopy(_VALID_SETTINGS)
        body.update(copy.deepcopy(changes))
        return body

    return make
