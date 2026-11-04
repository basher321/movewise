"""The notification outbox (spec B08). queue_message is the only way any code queues a message:
one email row (if there is an email) and one WhatsApp row (if there is a phone), written in the
caller's transaction. The worker sends them later."""

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.licence import Module

_INSERT = text(
    "INSERT INTO notifications (channel, to_address, to_name, module, event, subject, body, application_id) "
    "VALUES (:channel, :to_address, :to_name, :module, :event, :subject, :body, :application_id)"
)

MAX_SUBJECT = 200
# Events whose message carries a one-time code; the code is masked everywhere but the message itself.
CODE_EVENTS = ("email_code", "reset_code")
_CODE = re.compile(r"\b\d{6}\b")
# B15: the one-time token in a "Forgot password?" link is masked the same way.
LINK_EVENTS = ("password_reset_link",)
_LINK_TOKEN = re.compile(r"(token=)[A-Za-z0-9_-]+")


def queue_message(
    conn: Connection,
    to_name: str,
    email: str | None,
    phone: str | None,
    module: Module | None,
    event: str,
    subject: str,
    body: str,
    application_id: Any = None,
) -> None:
    subject = subject[:MAX_SUBJECT]
    common = {"to_name": to_name, "module": module, "event": event, "application_id": application_id}
    if email:
        conn.execute(_INSERT, {**common, "channel": "email", "to_address": email, "subject": subject, "body": body})
    if phone:
        whatsapp_body = f"{subject}\n{body}" if subject else body
        conn.execute(_INSERT, {**common, "channel": "whatsapp", "to_address": phone, "subject": "", "body": whatsapp_body})


def mask_codes(event: str, value: str) -> str:
    if event in LINK_EVENTS:
        return _LINK_TOKEN.sub(r"\1••••••", value)
    return _CODE.sub("••••••", value) if event in CODE_EVENTS else value
