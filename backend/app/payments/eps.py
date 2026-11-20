"""EPS (Easy Payment System) client (spec B26).

Follows the EPS Merchant API Integration Guide V4/V5 (January 2024) and what the EPS sandbox
answered on 2026-11-19 (spec B26 Decisions 3):
- Token: POST {base}/v1/Auth/GetToken {userName, password}, x-hash of userName.
- Start: POST {base}/v1/EPSEngine/InitializeEPS, x-hash of merchantTransactionId + Bearer token.
  merchantId is not sent (the sandbox refuses every start that has it).
- Status: GET {base}/v1/EPSEngine/CheckMerchantTransactionStatus?merchantTransactionId=...,
  x-hash of merchantTransactionId + Bearer token.
- Errors come back as HTTP 200 with ErrorCode set; a wrong or expired token gives HTTP 302 or 401.
x-hash = Base64(HMAC-SHA512(key = hash key as UTF-8, message = value as UTF-8)).
"""

import base64
import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.payments.gateway import GatewayConfig, GatewayError, http_client, taka

SANDBOX_BASE = "https://sandboxpgapi.eps.com.bd"
LIVE_BASE = "https://pgapi.eps.com.bd"
DHAKA = ZoneInfo("Asia/Dhaka")
DEFAULT_LIFETIME = 30 * 60.0
RETRY_PAUSE = 1.0

_tokens: dict[tuple[bool, str], tuple[str, float]] = {}
_lock = threading.Lock()


class TokenRejected(GatewayError):
    """EPS did not accept the token (HTTP 302 / 401)."""


class StartRefused(GatewayError):
    """InitializeEPS answered ErrorCode 500, which the sandbox sometimes does for a valid request."""


@dataclass(frozen=True)
class Customer:
    name: str
    email: str
    phone: str
    address: str
    city: str
    country: str


def base_url(config: GatewayConfig) -> str:
    return SANDBOX_BASE if config.sandbox else LIVE_BASE


def clear_tokens() -> None:
    with _lock:
        _tokens.clear()


def known_tokens() -> tuple[str, ...]:
    """Tokens held now, so scrub() can remove them from anything stored."""
    with _lock:
        return tuple(token for token, _ in _tokens.values())


def x_hash(hash_key: str, value: str) -> str:
    digest = hmac.new(hash_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha512).digest()
    return base64.b64encode(digest).decode("ascii")


def _read(response: httpx.Response) -> dict[str, Any]:
    if response.status_code in (301, 302, 303, 401):
        raise TokenRejected("EPS did not accept the sign-in token.")
    try:
        data: Any = response.json()
    except ValueError:
        raise GatewayError("EPS answer was not readable.") from None
    if not isinstance(data, dict):
        raise GatewayError("EPS answer was not readable.")
    return data


def _expiry(value: Any) -> float:
    """Seconds (time.monotonic based) until a minute before the token expires.
    expireDate has no time zone and is Asia/Dhaka time."""
    lifetime = DEFAULT_LIFETIME
    try:
        expires = datetime.fromisoformat(str(value)[:26]).replace(tzinfo=DHAKA)
        lifetime = (expires - datetime.now(DHAKA)).total_seconds()
    except (TypeError, ValueError):
        pass
    return time.monotonic() + max(lifetime - 60, 30)


def _token(config: GatewayConfig, fresh: bool = False) -> str:
    username = config.secrets["username"]
    key = (config.sandbox, username)
    with _lock:
        cached = _tokens.get(key)
        if cached and cached[1] > time.monotonic() and not fresh:
            return cached[0]
    try:
        with http_client() as client:
            response = client.post(
                f"{base_url(config)}/v1/Auth/GetToken",
                headers={"Accept": "application/json", "x-hash": x_hash(config.secrets["hash_key"], username)},
                json={"userName": username, "password": config.secrets["password"]},
            )
    except httpx.HTTPError:
        raise GatewayError("EPS did not answer.") from None
    data = _read(response)
    token = data.get("token")
    if not token or data.get("errorCode") not in (None, "", 0):
        raise GatewayError("EPS refused the sign-in.")
    with _lock:
        _tokens[key] = (str(token), _expiry(data.get("expireDate")))
    return str(token)


def _call(config: GatewayConfig, method: str, path: str, hash_of: str, **kwargs: Any) -> dict[str, Any]:
    """One signed call; a rejected token is renewed once and the call repeated once."""
    for attempt in (0, 1):
        token = _token(config, fresh=attempt == 1)
        headers = {
            "Accept": "application/json",
            "x-hash": x_hash(config.secrets["hash_key"], hash_of),
            "Authorization": f"Bearer {token}",
        }
        try:
            with http_client() as client:
                response = client.request(method, f"{base_url(config)}{path}", headers=headers, **kwargs)
        except httpx.HTTPError:
            raise GatewayError("EPS did not answer.") from None
        try:
            return _read(response)
        except TokenRejected:
            if attempt == 1:
                raise
    raise GatewayError("EPS did not answer.")  # pragma: no cover


def start(
    config: GatewayConfig,
    tran_id: str,
    amount_poisha: int,
    purpose: str,
    customer: Customer,
    urls: dict[str, str],
    ip_address: str,
    payment_id: str,
) -> tuple[str, str]:
    """Returns (EPS TransactionId, RedirectURL). StartRefused for ErrorCode 500."""
    body = {
        "storeId": config.secrets["store_id"],
        "CustomerOrderId": tran_id,
        "merchantTransactionId": tran_id,
        "transactionTypeId": 1,
        "financialEntityId": 0,
        "transitionStatusId": 0,
        # Text with 2 decimals (the sandbox accepts it; no float for money).
        "totalAmount": taka(amount_poisha),
        "ipAddress": ip_address[:45] or "0.0.0.0",
        "version": "1",
        "successUrl": urls["success"],
        "failUrl": urls["fail"],
        "cancelUrl": urls["cancel"],
        "customerName": customer.name[:100],
        "customerEmail": customer.email[:100],
        "CustomerAddress": (customer.address or customer.city or "Dhaka")[:200],
        "CustomerCity": (customer.city or "Dhaka")[:50],
        "CustomerState": (customer.city or "Dhaka")[:50],
        "CustomerPostcode": "1000",
        "CustomerCountry": "BD",
        "CustomerPhone": customer.phone[:20],
        "ProductName": purpose[:200],
        "ProductProfile": "non-physical-goods",
        "ProductCategory": "Service fee",
        "NoOfItem": "1",
        "ShippingMethod": "NO",
        "ValueA": payment_id,
    }
    data = _call(config, "POST", "/v1/EPSEngine/InitializeEPS", tran_id, json=body)
    session, url = data.get("TransactionId"), data.get("RedirectURL")
    if session and url and data.get("ErrorCode") in (None, "", 0):
        return str(session), str(url)
    if str(data.get("ErrorCode")) == "500":
        raise StartRefused("EPS could not start the payment.")
    raise GatewayError(f"EPS refused the payment. {data.get('ErrorMessage') or ''}".strip())


def status(config: GatewayConfig, tran_id: str) -> dict[str, Any]:
    return _call(
        config,
        "GET",
        "/v1/EPSEngine/CheckMerchantTransactionStatus",
        tran_id,
        params={"merchantTransactionId": tran_id},
    )
