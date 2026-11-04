"""b09, b10, b11, b12, b17 (settings part) and the settings edge cases."""

import copy
import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import crypto
from app.crypto import encrypt
from app.routers import settings as settings_router

BKASH_SECRETS = {
    "app_key": "bk-app-key-plain-111",
    "app_secret": "bk-app-secret-plain-222",
    "username": "bk-user-plain-333",
    "password": "bk-pass-plain-444",
}
SECRET_WORDS = ("key", "password", "secret", "token", "api_key", "store_id", "merchant_id", "username")


def _audit_count(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one())


def _bkash_on(body: dict[str, Any], **secrets: str) -> dict[str, Any]:
    body = copy.deepcopy(body)
    body["gateways"]["bkash"].update({"enabled": True, **secrets})
    return body


def _ciphertexts(conn: Connection, prefix: str) -> dict[str, str]:
    rows = conn.execute(
        text("SELECT name, ciphertext FROM settings_secrets WHERE name LIKE :prefix"),
        {"prefix": prefix + "%"},
    )
    return {name: ciphertext for name, ciphertext in rows}


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


# ---------- b09 ----------


def test_one_settings_row_and_one_licence_row_with_modules_off(conn: Connection) -> None:
    assert conn.execute(text("SELECT count(*) FROM settings")).scalar_one() == 1
    licence = conn.execute(
        text("SELECT count(*), bool_or(module_course OR module_study OR module_job), max(key) FROM licence")
    ).one()
    assert tuple(licence) == (1, False, None)


# ---------- b10 ----------


def test_public_settings_have_no_secret_field(client: TestClient) -> None:
    response = client.get("/api/settings/public")
    assert response.status_code == 200
    keys = _keys(response.json())
    assert not keys & set(SECRET_WORDS)
    assert {"name", "logo_url", "hero_url", "logo", "hero_image"} <= keys


def test_full_settings_show_secrets_only_as_saved(client: TestClient, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    body = client.get("/api/settings").json()
    secrets = [
        *(body["gateways"][g][f] for g, fields in settings_router.GATEWAY_SECRETS.items() for f in fields),
        body["mail"]["smtp_password"],
        body["whatsapp"]["token"],
    ]
    assert len(secrets) == 10
    assert all(isinstance(s, dict) and set(s) == {"saved"} for s in secrets)


# ---------- b11 ----------


def test_bkash_secrets_required_saved_encrypted_and_kept(
    client: TestClient,
    conn: Connection,
    act_as: Callable[..., Any],
    settings_body: Callable[..., dict[str, Any]],
) -> None:
    act_as("super_admin")
    response = client.put("/api/settings", json=_bkash_on(settings_body()))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert "bKash" in response.json()["message"]

    response = client.put("/api/settings", json=_bkash_on(settings_body(), **BKASH_SECRETS))
    assert response.status_code == 200
    stored = _ciphertexts(conn, "bkash.")
    assert len(stored) == 4
    for field, plain in BKASH_SECRETS.items():
        name = f"bkash.{field}"
        assert stored[name] != plain and plain not in stored[name]
        assert crypto.decrypt(name, stored[name]) == plain

    response = client.put("/api/settings", json=_bkash_on(settings_body()))
    assert response.status_code == 200
    assert _ciphertexts(conn, "bkash.") == stored
    assert response.json()["gateways"]["bkash"]["app_key"] == {"saved": True}
    assert BKASH_SECRETS["app_key"] not in response.text


def test_validation_rules(
    client: TestClient, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]
) -> None:
    act_as("super_admin")
    no_payment = settings_body()
    no_payment["gateways"]["manual"]["enabled"] = False
    bad_fee = settings_body(default_fee_poisha={"study": 0, "job": 100000})
    for body, words in [
        (settings_body(name="  "), "Company name"),
        (settings_body(brand_color="blue"), "Brand colour"),
        (settings_body(invoice_prefix=""), "Invoice prefix"),
        (settings_body(stats=[{"number": "1", "label": "a"}]), "3 stats"),
        (settings_body(email="not-an-email"), "valid email"),
        (bad_fee, "Default fees"),
        (no_payment, "payment method"),
    ]:
        response = client.put("/api/settings", json=body)
        assert response.status_code == 422, words
        assert response.json()["code"] == "VALIDATION"
        assert words in response.json()["message"]


# ---------- b12 ----------


def test_put_settings_needs_super_admin(
    client: TestClient, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]
) -> None:
    response = client.put("/api/settings", json=settings_body())
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"

    act_as("admin")
    response = client.put("/api/settings", json=settings_body())
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_sign_in_is_checked_before_the_body(client: TestClient) -> None:
    response = client.put("/api/settings", content=b"{not json", headers={"content-type": "application/json"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


# ---------- b17 (settings part) ----------


def test_settings_save_writes_one_audit_row_with_field_names_only(
    client: TestClient,
    conn: Connection,
    act_as: Callable[..., Any],
    settings_body: Callable[..., dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    act_as("super_admin")
    before = _audit_count(conn)
    response = client.put("/api/settings", json=_bkash_on(settings_body(), **BKASH_SECRETS))
    assert response.status_code == 200
    assert _audit_count(conn) == before + 1

    detail = conn.execute(
        text("SELECT detail FROM audit_log WHERE action = 'settings.saved' AND created_at >= now()")
    ).scalar_one()
    assert detail.startswith("Settings saved: ")
    assert "gateways.bkash.app_key" in detail
    rows = conn.execute(text("SELECT action || ' ' || detail || ' ' || by_name FROM audit_log")).scalars().all()
    for plain in BKASH_SECRETS.values():
        assert all(plain not in row for row in rows)
        assert plain not in caplog.text


def test_database_error_while_saving_secrets_logs_no_secret(
    client: TestClient,
    act_as: Callable[..., Any],
    settings_body: Callable[..., dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.DEBUG)
    def failing(conn: Any, name: str, value: str) -> None:
        # A database error while saving (the app only ever sends the encrypted value).
        conn.execute(
            text("INSERT INTO settings_secrets (name, ciphertext) VALUES (:name, CAST(:ciphertext AS integer))"),
            {"name": name, "ciphertext": encrypt(name, value)},
        )

    monkeypatch.setattr(settings_router, "save_secret", failing)
    act_as("super_admin")
    response = client.put("/api/settings", json=_bkash_on(settings_body(), **BKASH_SECRETS))
    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL", "message": "Something went wrong."}
    for plain in BKASH_SECRETS.values():
        assert plain not in caplog.text
        assert plain not in response.text


# ---------- Edge cases ----------


def test_changed_secret_key_shows_secret_as_unreadable(
    client: TestClient,
    act_as: Callable[..., Any],
    settings_body: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    act_as("super_admin")
    assert client.put("/api/settings", json=_bkash_on(settings_body(), **BKASH_SECRETS)).status_code == 200

    other_key = crypto.derive_key("a-different-secret-key-for-this-test")
    monkeypatch.setattr(crypto, "_key", lambda: other_key)
    body = client.get("/api/settings").json()
    assert body["gateways"]["bkash"]["app_key"] == {"saved": False, "unreadable": True}
    assert body["gateways"]["sslcommerz"]["store_id"] == {"saved": False}

    # An unreadable secret does not count as saved: bKash must be given its secrets again.
    response = client.put("/api/settings", json=_bkash_on(settings_body()))
    assert response.status_code == 422


def test_missing_settings_row_is_internal_and_logged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings_router, "_fetch_settings_row", lambda conn: None)
    response = client.get("/api/settings/public")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL"
    assert "settings row missing" in caplog.text


def test_saved_values_come_back(
    client: TestClient, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]
) -> None:
    act_as("super_admin")
    body = settings_body(name="Saved Name", brand_color="#0EA5A4", default_fee_poisha={"study": 250000, "job": 300000})
    assert client.put("/api/settings", json=body).status_code == 200
    public = client.get("/api/settings/public").json()
    assert (public["name"], public["brand_color"]) == ("Saved Name", "#0EA5A4")
    assert public["default_fee_poisha"] == {"study": 250000, "job": 300000, "visa": 100000}
    # jsonb does not keep key order inside each object, so compare values, not text.
    assert public["stats"] == body["stats"]
