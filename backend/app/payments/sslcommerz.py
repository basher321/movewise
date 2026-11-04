"""SSLCommerz API v4 client (spec B07, checked against developer.sslcommerz.com/doc/v4).

Start: form POST to {base}/gwprocess/v4/api.php; the payer is sent to GatewayPageURL.
Confirm: GET {base}/validator/api/validationserverAPI.php with val_id; only VALID or VALIDATED
with the same tran_id, amount and currency BDT is accepted (checked by the service).
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.payments.gateway import GatewayConfig, GatewayError, http_client, taka

SANDBOX_BASE = "https://sandbox.sslcommerz.com"
LIVE_BASE = "https://securepay.sslcommerz.com"


def base_url(config: GatewayConfig) -> str:
    return SANDBOX_BASE if config.sandbox else LIVE_BASE


@dataclass(frozen=True)
class Customer:
    name: str
    email: str
    phone: str
    city: str
    country: str


def start(
    config: GatewayConfig,
    tran_id: str,
    amount_poisha: int,
    purpose: str,
    customer: Customer,
    urls: dict[str, str],
) -> tuple[str, str]:
    """Returns (GatewayPageURL, sessionkey)."""
    form = {
        "store_id": config.secrets["store_id"],
        "store_passwd": config.secrets["store_password"],
        "total_amount": taka(amount_poisha),
        "currency": "BDT",
        "tran_id": tran_id,
        "success_url": urls["success"],
        "fail_url": urls["fail"],
        "cancel_url": urls["cancel"],
        "ipn_url": urls["ipn"],
        "cus_name": customer.name[:50],
        "cus_email": customer.email[:50],
        "cus_phone": customer.phone[:20],
        # Mandatory in the v4 docs (B07 decisions note).
        "cus_add1": (customer.city or "Dhaka")[:50],
        "cus_city": (customer.city or "Dhaka")[:50],
        "cus_postcode": "1000",
        "cus_country": (customer.country or "Bangladesh")[:50],
        "shipping_method": "NO",
        "num_of_item": "1",
        "product_name": purpose[:255],
        "product_category": "Service fee",
        "product_profile": "non-physical-goods",
    }
    try:
        with http_client() as client:
            response = client.post(f"{base_url(config)}/gwprocess/v4/api.php", data=form)
        data: Any = response.json()
    except (httpx.HTTPError, ValueError):
        raise GatewayError("SSLCommerz did not answer.") from None
    if not isinstance(data, dict) or data.get("status") != "SUCCESS" or not data.get("GatewayPageURL"):
        reason = str(data.get("failedreason", "")) if isinstance(data, dict) else ""
        raise GatewayError(f"SSLCommerz refused the payment. {reason}".strip())
    return str(data["GatewayPageURL"]), str(data.get("sessionkey", ""))


def validate(config: GatewayConfig, val_id: str) -> dict[str, Any]:
    params = {
        "val_id": val_id,
        "store_id": config.secrets["store_id"],
        "store_passwd": config.secrets["store_password"],
        "format": "json",
        "v": "1",
    }
    try:
        with http_client() as client:
            response = client.get(f"{base_url(config)}/validator/api/validationserverAPI.php", params=params)
        data: Any = response.json()
    except (httpx.HTTPError, ValueError):
        raise GatewayError("SSLCommerz validation did not answer.") from None
    if not isinstance(data, dict):
        raise GatewayError("SSLCommerz validation answer was not readable.")
    return data
