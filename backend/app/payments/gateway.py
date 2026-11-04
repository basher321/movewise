"""Shared pieces for the payment gateway clients (spec B07).

- One httpx client factory with a 20-second timeout. Tests set TRANSPORT to a fake transport,
  so they never call the internet.
- Gateway secrets are read from settings_secrets and decrypted only when a call needs them.
- scrub() removes secrets, tokens and card data before anything is stored or logged.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.crypto import DecryptError, decrypt

TIMEOUT_SECONDS = 20.0
TRANSPORT: httpx.BaseTransport | None = None

# httpx logs every request URL at INFO and httpcore logs headers at DEBUG. The SSLCommerz
# validation URL carries the store password and bKash headers carry the token, so these
# loggers never write below WARNING.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

Gateway = Literal["sslcommerz", "bkash"]

SECRET_FIELDS: dict[Gateway, tuple[str, ...]] = {
    "sslcommerz": ("store_id", "store_password"),
    "bkash": ("app_key", "app_secret", "username", "password"),
}

# Keys never stored in payment_events or logs, whatever the gateway sends back.
_SECRET_KEY_PARTS = ("passwd", "password", "secret", "token", "app_key", "x-app-key", "username", "store_id")
_CARD_KEYS = {"card_no", "card_number", "cardnumber", "pan", "cvv"}


class GatewayError(Exception):
    """The gateway could not be reached or its answer was not usable. The message has no secrets."""


@dataclass(frozen=True)
class GatewayConfig:
    sandbox: bool
    secrets: dict[str, str]


def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, transport=TRANSPORT)


def gateway_config(conn: Connection, gateway: Gateway) -> GatewayConfig | None:
    """The sandbox flag and decrypted secrets, or None when any secret is missing or unreadable."""
    sandbox = bool(
        conn.execute(text(f"SELECT {gateway}_sandbox FROM settings WHERE singleton = 'settings'")).scalar_one()
    )
    names = [f"{gateway}.{field}" for field in SECRET_FIELDS[gateway]]
    stored = dict(
        conn.execute(
            text("SELECT name, ciphertext FROM settings_secrets WHERE name = ANY(:names)"), {"names": names}
        ).all()
    )
    secrets: dict[str, str] = {}
    for field in SECRET_FIELDS[gateway]:
        name = f"{gateway}.{field}"
        if name not in stored:
            return None
        try:
            secrets[field] = decrypt(name, stored[name])
        except DecryptError:
            return None
    return GatewayConfig(sandbox=sandbox, secrets=secrets)


def scrub(data: Any, secret_values: tuple[str, ...] = ()) -> Any:
    """A copy of data without secret keys, card numbers or any known secret value."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if lowered in _CARD_KEYS or any(part in lowered for part in _SECRET_KEY_PARTS):
                continue
            out[str(key)] = scrub(value, secret_values)
        return out
    if isinstance(data, list):
        return [scrub(item, secret_values) for item in data]
    if isinstance(data, str):
        for secret in secret_values:
            if secret and secret in data:
                data = data.replace(secret, "***")
        return data
    if data is None or isinstance(data, (int, float, bool)):
        return data
    return str(data)


def taka(poisha: int) -> str:
    """Amount for a gateway: taka with 2 decimals, from whole poisha (no float)."""
    return f"{poisha // 100}.{poisha % 100:02d}"


def poisha_from_taka(value: Any) -> int | None:
    """'1000.00' -> 100000. None when the value is not a plain amount with at most 2 decimals."""
    raw = str(value).strip()
    if not raw or raw.count(".") > 1:
        return None
    whole, _, frac = raw.partition(".")
    if not whole.isdigit() or (frac and (not frac.isdigit() or len(frac) > 2)):
        return None
    return int(whole) * 100 + int((frac + "00")[:2])
