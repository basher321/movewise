"""Encrypted secrets: the 0002 names live in settings_secrets, later names in app_secrets (0008).
Values are decrypted only when a call needs them and never returned by the API."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.crypto import DecryptError, decrypt, encrypt

# Names allowed by the CHECK list of settings_secrets (0002).
LEGACY_NAMES = frozenset(
    {
        "sslcommerz.store_id", "sslcommerz.store_password",
        "bkash.app_key", "bkash.app_secret", "bkash.username", "bkash.password",
        "nagad.merchant_id", "nagad.private_key",
        "mail.api_key", "whatsapp.token",
    }
)

_ALL = text("SELECT name, ciphertext FROM settings_secrets UNION ALL SELECT name, ciphertext FROM app_secrets")


def _table(name: str) -> str:
    return "settings_secrets" if name in LEGACY_NAMES else "app_secrets"


def stored_secrets(conn: Connection) -> dict[str, str]:
    """name -> ciphertext, from both tables."""
    return {name: ciphertext for name, ciphertext in conn.execute(_ALL)}


def read_secret(conn: Connection, name: str) -> str | None:
    ciphertext = conn.execute(
        text(f"SELECT ciphertext FROM {_table(name)} WHERE name = :n"), {"n": name}
    ).scalar_one_or_none()
    if ciphertext is None:
        return None
    try:
        return decrypt(name, ciphertext)
    except DecryptError:
        return None


def save_secret(conn: Connection, name: str, value: str) -> None:
    table = _table(name)
    conn.execute(
        text(
            f"INSERT INTO {table} (name, ciphertext) VALUES (:n, :c) "
            "ON CONFLICT (name) DO UPDATE SET ciphertext = EXCLUDED.ciphertext"
        ),
        {"n": name, "c": encrypt(name, value)},
    )
