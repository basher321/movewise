"""WhatsApp Cloud API (spec B08), checked against Meta's docs on 2026-11-01:
POST https://graph.facebook.com/<version>/<phone number id>/messages with
Authorization: Bearer <token>, messaging_product "whatsapp", recipient_type "individual",
type "template", template {name, language {code}, components [body with one text parameter]}.
The template must be approved in WhatsApp Manager and have one body variable {{1}}.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.notify.email_smtp import SendResult

TIMEOUT_SECONDS = 20.0
MAX_TEXT = 1000
TRANSPORT: httpx.BaseTransport | None = None

for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)


@dataclass(frozen=True)
class WhatsappConfig:
    phone_number_id: str
    token: str
    template_name: str
    template_language: str
    api_version: str


def international(phone: str) -> str | None:
    """01XXXXXXXXX -> 8801XXXXXXXXX; +88 / 88 forms kept; other countries as digits. None if invalid."""
    digits = re.sub(r"[\s()-]", "", phone)
    if re.fullmatch(r"01[3-9]\d{8}", digits):
        return "88" + digits
    if re.fullmatch(r"\+?8801[3-9]\d{8}", digits):
        return digits.lstrip("+")
    if re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        return digits[1:]
    return None


def shorten(body: str) -> str:
    return body if len(body) <= MAX_TEXT else body[: MAX_TEXT - 1] + "…"


def send(config: WhatsappConfig, phone: str, body: str) -> SendResult:
    to = international(phone)
    if to is None:
        return SendResult(ok=False, temporary=False, error="Invalid phone number")
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": config.template_name,
            "language": {"code": config.template_language},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": shorten(body)}]}],
        },
    }
    url = f"https://graph.facebook.com/{config.api_version}/{config.phone_number_id}/messages"
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=TRANSPORT) as client:
            response = client.post(url, json=payload, headers={"Authorization": f"Bearer {config.token}"})
    except httpx.HTTPError as exc:
        return SendResult(ok=False, temporary=True, error=type(exc).__name__)
    if response.status_code == 429 or response.status_code >= 500:
        return SendResult(ok=False, temporary=True, error=f"WhatsApp HTTP {response.status_code}")
    if response.status_code >= 400:
        message = ""
        try:
            message = str(response.json().get("error", {}).get("message", ""))
        except ValueError:
            pass
        message = message.replace(config.token, "***") if config.token else message
        return SendResult(ok=False, temporary=False, error=f"WhatsApp HTTP {response.status_code} {message}"[:200].strip())
    try:
        provider_id = str(response.json()["messages"][0]["id"])
    except (ValueError, KeyError, IndexError, TypeError):
        provider_id = None
    return SendResult(ok=True, provider_id=provider_id)
