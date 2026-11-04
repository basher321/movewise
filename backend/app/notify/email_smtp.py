"""Email by SMTP with Python's smtplib and email.message (spec B08, no new package).

Plain text plus a simple HTML version: company name at the top, the body escaped (never raw
HTML from data), and a footer with the company address.
"""

import html
import smtplib
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    security: str  # starttls | ssl | none
    username: str
    password: str
    sender_name: str
    sender_email: str
    reply_to: str
    company_name: str
    company_address: str


@dataclass(frozen=True)
class SendResult:
    ok: bool
    temporary: bool = False
    error: str = ""
    provider_id: str | None = None


def _connect(config: MailConfig) -> smtplib.SMTP:
    context = ssl.create_default_context()
    if config.security == "ssl":
        return smtplib.SMTP_SSL(config.host, config.port, timeout=TIMEOUT_SECONDS, context=context)
    client = smtplib.SMTP(config.host, config.port, timeout=TIMEOUT_SECONDS)
    if config.security == "starttls":
        client.starttls(context=context)
    return client


# Tests replace this with a fake SMTP server.
SMTP_FACTORY: Callable[[MailConfig], smtplib.SMTP] = _connect


def build_message(config: MailConfig, to: str, to_name: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((config.sender_name or config.company_name, config.sender_email))
    message["To"] = formataddr((to_name, to)) if to_name else to
    if config.reply_to:
        message["Reply-To"] = config.reply_to
    message["Subject"] = subject[:200]
    message["Message-ID"] = make_msgid(domain=config.sender_email.split("@")[-1] or None)
    message.set_content(body)
    paragraphs = "".join(
        f"<p style=\"margin:0 0 12px\">{html.escape(part).replace(chr(10), '<br>')}</p>"
        for part in body.split("\n\n")
    )
    footer = html.escape(config.company_address) if config.company_address else ""
    message.add_alternative(
        "<!doctype html><html><body style=\"font-family:Arial,sans-serif;color:#1f2937;line-height:1.5\">"
        f"<h2 style=\"margin:0 0 16px\">{html.escape(config.company_name)}</h2>{paragraphs}"
        f"<hr style=\"border:none;border-top:1px solid #e5e7eb;margin:20px 0\">"
        f"<p style=\"font-size:12px;color:#6b7280\">{html.escape(config.company_name)}"
        f"{'<br>' + footer if footer else ''}</p></body></html>",
        subtype="html",
    )
    return message


def _short(error: object, config: MailConfig) -> str:
    text = str(error).replace(config.password, "***") if config.password else str(error)
    return text[:200]


def send(config: MailConfig, to: str, to_name: str, subject: str, body: str) -> SendResult:
    message = build_message(config, to, to_name, subject, body)
    try:
        client = SMTP_FACTORY(config)
        try:
            if config.username:
                client.login(config.username, config.password)
            refused = client.send_message(message)
        finally:
            try:
                client.quit()
            except (smtplib.SMTPException, OSError):
                pass
    except smtplib.SMTPRecipientsRefused:
        return SendResult(ok=False, temporary=False, error="The email address was refused.")
    except smtplib.SMTPResponseException as exc:
        temporary = 400 <= exc.smtp_code < 500
        return SendResult(ok=False, temporary=temporary, error=f"SMTP {exc.smtp_code}")
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, TimeoutError, OSError) as exc:
        return SendResult(ok=False, temporary=True, error=_short(type(exc).__name__, config))
    except smtplib.SMTPException as exc:
        return SendResult(ok=False, temporary=False, error=_short(type(exc).__name__, config))
    if refused:
        return SendResult(ok=False, temporary=False, error="The email address was refused.")
    return SendResult(ok=True, provider_id=str(message["Message-ID"]))
