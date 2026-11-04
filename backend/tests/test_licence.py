"""b14, b15, b16, b17 (licence part) and the licence edge cases."""

import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import licence
from app.auth.deps import require_module
from app.licence import INVALID_KEY, MODULES, make_key, today_dhaka
from conftest import PROJECT_DIR, LicenceKeys, new_client

MAKE_KEY = PROJECT_DIR / "tools" / "licence" / "make_key.py"


@pytest.fixture
def module_client(api: FastAPI) -> Iterator[TestClient]:
    """The app plus one test-only route per module, each behind require_module."""
    for module in MODULES:
        api.add_api_route(
            f"/api/_test/{module}",
            lambda: {"ok": True},
            methods=["GET"],
            dependencies=[Depends(require_module(module))],
        )
    with new_client(api) as client:
        yield client


def _make_key_cli(keys: LicenceKeys, modules: str, holder: str = "Test Holder Ltd") -> str:
    result = subprocess.run(
        [sys.executable, str(MAKE_KEY), "--private-key", str(keys.private_path), "--holder", holder, "--modules", modules],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _apply(client: TestClient, key: str) -> Any:
    return client.put("/api/licence", json={"key": key})


def _audit_count(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one())


def _flip(part: str) -> str:
    middle = len(part) // 2
    return part[:middle] + ("A" if part[middle] != "A" else "B") + part[middle + 1:]


# ---------- b14 ----------


def test_key_from_make_key_unlocks_study_and_job_only(
    module_client: TestClient, act_as: Callable[..., Any], licence_keys: LicenceKeys
) -> None:
    key = _make_key_cli(licence_keys, "study,job")
    assert key.startswith("MW1.") and key.count(".") == 2 and "\n" not in key

    act_as("super_admin")
    response = _apply(module_client, key)
    assert response.status_code == 200
    assert "key" not in response.json()

    view = module_client.get("/api/licence").json()
    assert view["modules"] == {"course": False, "study": True, "job": True, "visa": False}
    assert view["holder"] == "Test Holder Ltd"
    assert view["active"] is True and "key" not in view

    for role in ("admin", "super_admin"):
        act_as(role)
        refused = module_client.get("/api/_test/course")
        assert refused.status_code == 403
        assert refused.json()["code"] == "MODULE_NOT_LICENSED"
        assert module_client.get("/api/_test/study").status_code == 200
        assert module_client.get("/api/_test/job").status_code == 200


def test_full_view_shows_masked_key_to_super_admin_only(
    client: TestClient, act_as: Callable[..., Any], licence_keys: LicenceKeys
) -> None:
    key = make_key(licence_keys.private_key, "Holder", ["course"], today_dhaka(), None)
    act_as("super_admin")
    assert _apply(client, key).status_code == 200
    full = client.get("/api/licence/full")
    assert full.json()["key"] == f"{key[:8]}...{key[-6:]}"
    assert key not in full.text
    act_as("admin")
    assert client.get("/api/licence/full").status_code == 403


# ---------- b15 ----------


def test_tampered_foreign_and_expired_keys_are_not_valid(
    client: TestClient, act_as: Callable[..., Any], licence_keys: LicenceKeys
) -> None:
    today = today_dhaka()
    good = make_key(licence_keys.private_key, "Holder", ["study"], today, None)
    prefix, payload, signature = good.split(".")
    other = Ed25519PrivateKey.generate()
    bad_keys = {
        "changed payload": f"{prefix}.{_flip(payload)}.{signature}",
        "changed signature": f"{prefix}.{payload}.{_flip(signature)}",
        "other private key": make_key(other, "Holder", ["study"], today, None),
        "expired": make_key(licence_keys.private_key, "Holder", ["study"], today - timedelta(days=10), today - timedelta(days=1)),
        "no modules": make_key(licence_keys.private_key, "Holder", [], today, None),
        "bad format": "not-a-licence-key",
    }
    act_as("super_admin")
    for label, key in bad_keys.items():
        response = _apply(client, key)
        assert response.status_code == 422, label
        assert response.json() == {"code": "VALIDATION", "message": INVALID_KEY}, label
    assert _apply(client, good).status_code == 200


# ---------- b16 ----------


def test_expired_stored_licence_locks_every_module(
    module_client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    conn.execute(
        text(
            "UPDATE licence SET key = 'stored-earlier', holder = 'Holder', module_course = true, "
            "module_study = true, module_job = true, expires_at = :yesterday WHERE singleton = 'licence'"
        ),
        {"yesterday": today_dhaka() - timedelta(days=1)},
    )
    act_as("super_admin")
    for module in MODULES:
        response = module_client.get(f"/api/_test/{module}")
        assert response.status_code == 403, module
        assert response.json()["code"] == "MODULE_NOT_LICENSED"
    view = module_client.get("/api/licence").json()
    assert view["active"] is False
    assert view["modules"] == {"course": False, "study": False, "job": False, "visa": False}


# ---------- b17 (licence part) and edge cases ----------


def test_same_key_twice_writes_audit_and_changes_nothing_else(
    client: TestClient, conn: Connection, act_as: Callable[..., Any], licence_keys: LicenceKeys
) -> None:
    key = make_key(licence_keys.private_key, "Holder", ["study", "job"], today_dhaka(), None)
    act_as("super_admin")
    before = _audit_count(conn)
    assert _apply(client, key).status_code == 200
    assert _audit_count(conn) == before + 1
    row_query = text("SELECT key, holder, module_course, module_study, module_job, applied_at, applied_by FROM licence")
    first = conn.execute(row_query).one()

    act_as("super_admin")
    assert _apply(client, key).status_code == 200
    assert _audit_count(conn) == before + 2
    assert conn.execute(row_query).one() == first

    details = conn.execute(
        text("SELECT detail FROM audit_log WHERE action = 'licence.changed' AND created_at >= now() ORDER BY detail")
    ).scalars().all()
    assert details == ["Licence changed (none -> study, job)", "Licence changed (study, job -> study, job)"]
    assert all(key not in d for d in details)


def test_huge_key_is_refused_without_decoding(
    client: TestClient, act_as: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(licence, "b64url_decode", lambda part: calls.append(part) or b"")
    act_as("super_admin")
    response = _apply(client, "MW1." + "A" * 5000 + ".AAAA")
    assert response.status_code == 422
    assert response.json()["message"] == INVALID_KEY
    assert calls == []


def test_licence_endpoints_need_super_admin(
    client: TestClient, act_as: Callable[..., Any], licence_keys: LicenceKeys
) -> None:
    key = make_key(licence_keys.private_key, "Holder", ["study"], today_dhaka(), None)
    assert _apply(client, key).status_code == 401
    act_as("admin")
    assert _apply(client, key).status_code == 403
    assert client.get("/api/licence").status_code == 200
