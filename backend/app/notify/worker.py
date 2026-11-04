"""The outbox worker (spec B08).

Every 10 seconds: rows stuck "sending" for over 10 minutes go back to waiting; then up to 20
due messages are claimed with SELECT ... FOR UPDATE SKIP LOCKED (so two workers never take the
same row), marked sending and committed BEFORE the provider is called; the result is saved
right after. Temporary failures retry after 1, 5 and 30 minutes; after 4 tries the row is failed.
At most 30 emails and 30 WhatsApp messages per minute.

process_once takes a "run" function that executes one step in its own transaction, so tests
can run the same code inside their rolled-back test transaction.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from app.db.engine import get_engine
from app.notify import email_smtp, whatsapp
from app.notify.email_smtp import MailConfig, SendResult
from app.notify.whatsapp import WhatsappConfig
from app.secrets_store import read_secret

logger = logging.getLogger("app")

T = TypeVar("T")
Runner = Callable[[Callable[[Connection], T]], T]

INTERVAL_SECONDS = 10
BATCH = 20
PER_MINUTE = 30
MAX_TRIES = 4
RETRY_MINUTES = (1, 5, 30)
STALE_MINUTES = 10
NOT_SET_UP = {"email": "Email is not set up", "whatsapp": "WhatsApp is not set up"}


def engine_runner(step: Callable[[Connection], T]) -> T:
    with get_engine().begin() as conn:
        return step(conn)


# ---------------------------------------------------------------- configuration


def mail_config(conn: Connection) -> MailConfig | None:
    row = conn.execute(
        text(
            "SELECT smtp_host, smtp_port, smtp_security, smtp_username, mail_sender_name, mail_sender_email, "
            "email, name, address FROM settings WHERE singleton = 'settings'"
        )
    ).one()
    password = read_secret(conn, "mail.smtp_password")
    if not row.smtp_host or not row.mail_sender_email or not password:
        return None
    return MailConfig(
        host=row.smtp_host,
        port=row.smtp_port,
        security=row.smtp_security,
        username=row.smtp_username,
        password=password,
        sender_name=row.mail_sender_name,
        sender_email=row.mail_sender_email,
        reply_to=row.email,
        company_name=row.name,
        company_address=row.address,
    )


def whatsapp_config(conn: Connection) -> WhatsappConfig | None:
    row = conn.execute(
        text(
            "SELECT whatsapp_phone_number_id, whatsapp_template_name, whatsapp_template_language, "
            "whatsapp_api_version FROM settings WHERE singleton = 'settings'"
        )
    ).one()
    token = read_secret(conn, "whatsapp.token")
    if not row.whatsapp_phone_number_id or not row.whatsapp_template_name or not token:
        return None
    return WhatsappConfig(
        phone_number_id=row.whatsapp_phone_number_id,
        token=token,
        template_name=row.whatsapp_template_name,
        template_language=row.whatsapp_template_language,
        api_version=row.whatsapp_api_version,
    )


# ---------------------------------------------------------------- steps


def _release_stale(conn: Connection) -> None:
    conn.execute(
        text(
            "UPDATE notifications SET sending_since = NULL WHERE status = 'queued' "
            f"AND sending_since < now() - interval '{STALE_MINUTES} minutes'"
        )
    )


def _claim(conn: Connection) -> list[dict[str, Any]]:
    sent = dict(
        conn.execute(
            text(
                "SELECT channel, count(*) FROM notifications WHERE sent_at > now() - interval '1 minute' "
                "OR (sending_since IS NOT NULL AND status = 'queued') GROUP BY channel"
            )
        ).all()
    )
    room = {"email": PER_MINUTE - int(sent.get("email", 0)), "whatsapp": PER_MINUTE - int(sent.get("whatsapp", 0))}
    rows = conn.execute(
        text(
            "SELECT id, channel, to_address, to_name, event, subject, body, tries FROM notifications "
            "WHERE status = 'queued' AND sending_since IS NULL AND next_attempt_at <= now() "
            "ORDER BY next_attempt_at, at, id LIMIT :limit FOR UPDATE SKIP LOCKED"
        ),
        {"limit": BATCH},
    ).mappings().all()
    chosen = []
    for row in rows:
        if room[row["channel"]] > 0:
            room[row["channel"]] -= 1
            chosen.append(dict(row))
    if chosen:
        conn.execute(
            text("UPDATE notifications SET sending_since = clock_timestamp() WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": [r["id"] for r in chosen]},
        )
    return chosen


def _save(conn: Connection, row: dict[str, Any], result: SendResult | None) -> None:
    if result is None:
        # Not set up: keep waiting, try again in a minute; not counted as a try.
        conn.execute(
            text(
                "UPDATE notifications SET sending_since = NULL, last_error = :e, "
                "next_attempt_at = now() + interval '1 minute' WHERE id = :id"
            ),
            {"e": NOT_SET_UP[row["channel"]], "id": row["id"]},
        )
        return
    tries = int(row["tries"]) + 1
    if result.ok:
        conn.execute(
            text(
                "UPDATE notifications SET status = 'sent', sent_at = clock_timestamp(), sending_since = NULL, "
                "tries = :t, last_error = '', provider_message_id = :p WHERE id = :id"
            ),
            {"t": tries, "p": result.provider_id, "id": row["id"]},
        )
        return
    error = result.error[:300]
    if result.temporary and tries < MAX_TRIES:
        conn.execute(
            text(
                "UPDATE notifications SET sending_since = NULL, tries = :t, last_error = :e, "
                "next_attempt_at = now() + :wait WHERE id = :id"
            ),
            {"t": tries, "e": error, "wait": timedelta(minutes=RETRY_MINUTES[tries - 1]), "id": row["id"]},
        )
        return
    conn.execute(
        text(
            "UPDATE notifications SET status = 'failed', sending_since = NULL, tries = :t, last_error = :e "
            "WHERE id = :id"
        ),
        {"t": tries, "e": error, "id": row["id"]},
    )
    logger.warning("Notification %s failed: %s", row["id"], error)


def deliver(row: dict[str, Any], mail: MailConfig | None, wa: WhatsappConfig | None) -> SendResult | None:
    if row["channel"] == "email":
        if mail is None:
            return None
        return email_smtp.send(mail, row["to_address"], row["to_name"], row["subject"], row["body"])
    if wa is None:
        return None
    return whatsapp.send(wa, row["to_address"], row["body"])


def process_once(run: Runner[Any] = engine_runner) -> int:
    """One round. Returns how many messages were taken."""
    run(_release_stale)
    claimed: list[dict[str, Any]] = run(_claim)
    if not claimed:
        return 0
    configs: tuple[MailConfig | None, WhatsappConfig | None] = run(lambda c: (mail_config(c), whatsapp_config(c)))
    for row in claimed:
        try:
            result = deliver(row, *configs)
        except Exception:  # never let one message stop the round
            logger.exception("Notification %s could not be sent", row["id"])
            result = SendResult(ok=False, temporary=True, error="Unexpected error")
        run(lambda c, r=row, res=result: _save(c, r, res))
    return len(claimed)


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(process_once)
        except Exception:
            logger.exception("Notification worker round failed")
        await asyncio.sleep(INTERVAL_SECONDS)
