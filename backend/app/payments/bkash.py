"""bKash tokenized checkout client (spec B07).

The official bKash developer pages could not be opened on 2026-11-01, so this follows the spec
(tokenized checkout v1.2.0-beta). Test it in the bKash sandbox before going live.

Token: POST {base}/tokenized/checkout/token/grant, kept in memory until it expires.
Create: POST {base}/tokenized/checkout/create -> paymentID, bkashURL.
Execute: POST {base}/tokenized/checkout/execute; status: POST {base}/tokenized/checkout/payment/status.
"""

import threading
import time
from typing import Any

import httpx

from app.payments.gateway import GatewayConfig, GatewayError, http_client, taka

SANDBOX_BASE = "https://tokenized.sandbox.bka.sh/v1.2.0-beta"
LIVE_BASE = "https://tokenized.pay.bka.sh/v1.2.0-beta"

_tokens: dict[tuple[bool, str], tuple[str, float]] = {}
_lock = threading.Lock()


def base_url(config: GatewayConfig) -> str:
    return SANDBOX_BASE if config.sandbox else LIVE_BASE


def clear_tokens() -> None:
    with _lock:
        _tokens.clear()


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    try:
        with http_client() as client:
            response = client.post(url, headers={"Accept": "application/json", **headers}, json=body)
        data: Any = response.json()
    except (httpx.HTTPError, ValueError):
        raise GatewayError("bKash did not answer.") from None
    if not isinstance(data, dict):
        raise GatewayError("bKash answer was not readable.")
    return data


def _token(config: GatewayConfig) -> str:
    key = (config.sandbox, config.secrets["app_key"])
    with _lock:
        cached = _tokens.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
    data = _post(
        f"{base_url(config)}/tokenized/checkout/token/grant",
        {"username": config.secrets["username"], "password": config.secrets["password"]},
        {"app_key": config.secrets["app_key"], "app_secret": config.secrets["app_secret"]},
    )
    token = data.get("id_token")
    if not token:
        raise GatewayError("bKash refused the sign-in.")
    try:
        lifetime = float(data.get("expires_in", 3600))
    except (TypeError, ValueError):
        lifetime = 3600.0
    with _lock:
        # Renew a minute early.
        _tokens[key] = (str(token), time.monotonic() + max(lifetime - 60, 30))
    return str(token)


def _auth(config: GatewayConfig) -> dict[str, str]:
    return {"Authorization": _token(config), "X-APP-Key": config.secrets["app_key"]}


def create(config: GatewayConfig, tran_id: str, amount_poisha: int, phone: str, callback_url: str) -> tuple[str, str]:
    """Returns (paymentID, bkashURL)."""
    data = _post(
        f"{base_url(config)}/tokenized/checkout/create",
        _auth(config),
        {
            "mode": "0011",
            "payerReference": phone,
            "callbackURL": callback_url,
            "amount": taka(amount_poisha),
            "currency": "BDT",
            "intent": "sale",
            "merchantInvoiceNumber": tran_id,
        },
    )
    payment_id, url = data.get("paymentID"), data.get("bkashURL")
    if not payment_id or not url:
        raise GatewayError(f"bKash refused the payment. {data.get('statusMessage', '')}".strip())
    return str(payment_id), str(url)


def execute(config: GatewayConfig, payment_id: str) -> dict[str, Any]:
    return _post(f"{base_url(config)}/tokenized/checkout/execute", _auth(config), {"paymentID": payment_id})


def status(config: GatewayConfig, payment_id: str) -> dict[str, Any]:
    return _post(f"{base_url(config)}/tokenized/checkout/payment/status", _auth(config), {"paymentID": payment_id})
