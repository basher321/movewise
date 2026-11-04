"""Notifications for staff (spec B08): the delivery log, resend, and the Settings test buttons.

The list masks one-time codes. A row being sent has status 'queued' with sending_since set
(see migration 0008) and is shown as "sending".
"""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.deps import require_admin, require_super_admin
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.notify import email_smtp, whatsapp
from app.notify.outbox import mask_codes
from app.notify.worker import mail_config, whatsapp_config

router = APIRouter()

PAGE_SIZE = 50
STATUSES = ("queued", "sending", "sent", "failed")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _shown_status(row: RowMapping) -> str:
    if row["status"] == "queued" and row["sending_since"] is not None:
        return "sending"
    return str(row["status"])


def _view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "at": row["at"].isoformat(),
        "channel": row["channel"],
        "to": row["to_address"],
        "to_name": row["to_name"],
        "module": row["module"],
        "event": row["event"],
        "subject": mask_codes(row["event"], row["subject"]),
        "body": mask_codes(row["event"], row["body"]),
        "status": _shown_status(row),
        "tries": row["tries"],
        "sent_at": row["sent_at"].isoformat() if row["sent_at"] else None,
        "next_attempt_at": row["next_attempt_at"].isoformat(),
        "last_error": row["last_error"],
    }


@router.get("/admin/notifications")
def list_notifications(
    channel: str = "",
    status: str = "",
    q: str = "",
    page: int = 1,
    actor: Actor = Depends(require_admin),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    where = ["TRUE"]
    params: dict[str, Any] = {}
    if channel:
        if channel not in ("email", "whatsapp"):
            raise _invalid("Unknown channel.")
        where.append("channel = :channel")
        params["channel"] = channel
    if status:
        if status not in STATUSES:
            raise _invalid("Unknown status.")
        if status == "sending":
            where.append("status = 'queued' AND sending_since IS NOT NULL")
        elif status == "queued":
            where.append("status = 'queued' AND sending_since IS NULL")
        else:
            where.append("status = :status")
            params["status"] = status
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where.append("(to_address ILIKE :q OR to_name ILIKE :q OR subject ILIKE :q OR event ILIKE :q)")
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    clause = " AND ".join(where)
    total = int(conn.execute(text(f"SELECT count(*) FROM notifications WHERE {clause}"), params).scalar_one())
    rows = conn.execute(
        text(f"SELECT * FROM notifications WHERE {clause} ORDER BY at DESC, id LIMIT :l OFFSET :o"),
        {**params, "l": PAGE_SIZE, "o": (page - 1) * PAGE_SIZE},
    ).mappings()
    return {"items": [_view(r) for r in rows], "total": total, "page": page, "page_size": PAGE_SIZE}


@router.post("/admin/notifications/{notification_id}/resend")
def resend(
    notification_id: str, actor: Actor = Depends(require_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        uid = UUID(notification_id)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, "Message not found.") from None
    row = conn.execute(text("SELECT * FROM notifications WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Message not found.")
    shown = _shown_status(row)
    if shown in ("sent", "sending"):
        raise ApiError("CONFLICT", 409, f"This message is {shown}.")
    updated = conn.execute(
        text(
            "UPDATE notifications SET status = 'queued', next_attempt_at = now(), tries = 0, last_error = '' "
            "WHERE id = :id RETURNING *"
        ),
        {"id": uid},
    ).mappings().one()
    write_audit(conn, actor, "Message resent", f"{row['channel']} · {row['event']} · {row['to_address']}")
    return _view(updated)


class TestIn(BaseModel):
    to: str = Field(max_length=254)


@router.post("/admin/settings/test-email")
async def test_email(
    request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    to = parse_body(TestIn, await request.body()).to.strip()
    if not _EMAIL.fullmatch(to):
        raise _invalid("Please enter a valid email.")
    config = mail_config(conn)
    if config is None:
        result = email_smtp.SendResult(ok=False, error="Email is not set up")
    else:
        result = email_smtp.send(
            config, to, "", f"Test email from {config.company_name}",
            "This is a test email. If you can read it, email sending works.",
        )
    write_audit(conn, actor, "Test email sent", f"{to} · {'ok' if result.ok else 'failed'}")
    return {"ok": True} if result.ok else {"ok": False, "error": result.error}


@router.post("/admin/settings/test-whatsapp")
async def test_whatsapp(
    request: Request, actor: Actor = Depends(require_super_admin), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    to = parse_body(TestIn, await request.body()).to.strip()
    if whatsapp.international(to) is None:
        raise _invalid("Please enter a valid mobile number, like 01712345678.")
    config = whatsapp_config(conn)
    if config is None:
        result = email_smtp.SendResult(ok=False, error="WhatsApp is not set up")
    else:
        result = whatsapp.send(config, to, "This is a test message. If you can read it, WhatsApp sending works.")
    write_audit(conn, actor, "Test WhatsApp sent", f"{to} · {'ok' if result.ok else 'failed'}")
    return {"ok": True} if result.ok else {"ok": False, "error": result.error}
