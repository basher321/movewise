"""Staff messages to clients by email, WhatsApp or both (spec B20): one client, or a group.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Finance never sends client messages. Every send writes its notification rows (with sent_by)
and exactly one audit row in the same transaction; the worker delivers them as usual.
"""

import json
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.applications import STATUS_LABELS
from app.audit import Actor, write_audit
from app.auth.deps import ensure_section, get_current_actor
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULE_LABELS, Module
from app.notify.outbox import queue_message

router = APIRouter()

Channel = Literal["email", "whatsapp"]
MAX_SUBJECT = 200
MAX_BODY = 5000
MAX_RECIPIENTS = 1000
ENROLMENT_STATUSES = ("awaiting_payment", "active", "completed", "cancelled")


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


class MessageIn(BaseModel):
    channels: list[Channel] = Field(min_length=1, max_length=2)
    subject: str = Field(max_length=1000)
    body: str = Field(max_length=20_000)


class OneIn(MessageIn):
    account_id: str = Field(max_length=64)


class Filters(BaseModel):
    status: str | None = None
    stage: StrictInt | None = None
    item_id: str | None = None
    has_application: StrictBool | None = None
    enrolment_status: str | None = None


class GroupIn(BaseModel):
    module: Module
    filters: Filters = Field(default_factory=Filters)


class BulkIn(MessageIn):
    module: Module
    filters: Filters = Field(default_factory=Filters)
    expected_recipients: StrictInt


def _text(body: MessageIn) -> tuple[tuple[str, ...], str, str]:
    subject, message = body.subject.strip(), body.body.strip()
    if not subject or not message:
        raise _invalid("Please write the subject and the message.")
    if len(subject) > MAX_SUBJECT:
        raise _invalid(f"Subject must be at most {MAX_SUBJECT} characters.")
    if len(message) > MAX_BODY:
        raise _invalid(f"The message must be at most {MAX_BODY} characters.")
    return tuple(dict.fromkeys(body.channels)), subject, message


# ---------------------------------------------------------------- one client


@router.post("/admin/messages")
async def send_one(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, int]:
    body = parse_body(OneIn, await request.body())
    try:
        uid = UUID(body.account_id)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, "Account not found.") from None
    person = conn.execute(
        text("SELECT id, module, public_id, name, email, phone FROM applicant_accounts WHERE id = :id"), {"id": uid}
    ).mappings().one_or_none()
    if person is None:
        raise ApiError("NOT_FOUND", 404, "Account not found.")
    ensure_section(conn, actor, person["module"])
    channels, subject, message = _text(body)
    queued = queue_message(
        conn, person["name"], person["email"], person["phone"] or None, person["module"], "staff_message",
        subject, message, channels=channels, sent_by=actor.id,
    )
    if queued == 0:
        raise _invalid("This client has no email or phone number for the chosen channel.")
    write_audit(conn, actor, "message.sent", f"{person['public_id']} · {', '.join(channels)} · {subject}")
    return {"queued": queued}


# ---------------------------------------------------------------- a group


def _recipients(conn: Connection, module: Module, f: Filters) -> list[dict[str, Any]]:
    where = ["p.module = :module"]
    params: dict[str, Any] = {"module": module}
    item: UUID | None = None
    if f.item_id:
        try:
            item = UUID(f.item_id)
        except ValueError:
            raise _invalid("Unknown item.") from None
    if module == "course":
        if f.status is not None or f.stage is not None:
            raise _invalid("Training has no application status or stage; use the enrolment status.")
        cond = []
        if f.enrolment_status is not None:
            if f.enrolment_status not in ENROLMENT_STATUSES:
                raise _invalid("Unknown enrolment status.")
            cond.append("e.status = :enrolment_status")
            params["enrolment_status"] = f.enrolment_status
        if item is not None:
            cond.append("e.course_id = :item")
            params["item"] = item
        exists = "EXISTS (SELECT 1 FROM enrolments e WHERE e.applicant_id = p.id" + "".join(f" AND {c}" for c in cond) + ")"
        if cond or f.has_application is True:
            where.append(exists)
        elif f.has_application is False:
            where.append("NOT " + exists)
    else:
        if f.enrolment_status is not None:
            raise _invalid("Enrolment status is for Training only.")
        cond = []
        if f.status is not None:
            if f.status not in STATUS_LABELS:
                raise _invalid("Unknown status.")
            cond.append("a.status = :status")
            params["status"] = f.status
        if f.stage is not None:
            if f.stage < 0 or f.stage > 8:
                raise _invalid("Unknown stage.")
            cond.append("a.stage = :stage")
            params["stage"] = f.stage
        if item is not None:
            cond.append("COALESCE(a.university_id, a.vacancy_id, a.visa_program_id) = :item")
            params["item"] = item
        exists = "EXISTS (SELECT 1 FROM applications a WHERE a.applicant_id = p.id" + "".join(f" AND {c}" for c in cond) + ")"
        if cond or f.has_application is True:
            where.append(exists)
        elif f.has_application is False:
            where.append("NOT " + exists)
    sql = "SELECT p.id, p.name, p.email, p.phone FROM applicant_accounts p WHERE " + " AND ".join(where)
    return [dict(r) for r in conn.execute(text(sql + " ORDER BY p.created_at, p.id"), params).mappings()]


def _preview(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "recipients": len(rows),
        "with_email": sum(1 for r in rows if r["email"]),
        "with_whatsapp": sum(1 for r in rows if r["phone"]),
    }


@router.post("/admin/messages/bulk/preview")
async def preview_group(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, int]:
    body = parse_body(GroupIn, await request.body())
    ensure_section(conn, actor, body.module)
    return _preview(_recipients(conn, body.module, body.filters))


@router.post("/admin/messages/bulk")
async def send_group(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(BulkIn, await request.body())
    ensure_section(conn, actor, body.module)
    channels, subject, message = _text(body)
    rows = _recipients(conn, body.module, body.filters)
    if len(rows) > MAX_RECIPIENTS:
        raise _invalid(f"At most {MAX_RECIPIENTS} clients per message. Narrow the filters.")
    if not rows:
        raise _invalid("No client matches these filters.")
    if len(rows) != body.expected_recipients:
        raise ApiError("CONFLICT", 409, "The number of clients changed. Please check the list again.")
    filters = body.filters.model_dump(exclude_none=True)
    batch_id = conn.execute(
        text(
            "INSERT INTO message_batches (module, filters, channels, subject, body, recipients, sent_by) "
            "VALUES (:m, CAST(:f AS jsonb), CAST(:c AS text[]), :s, :b, :n, :by) RETURNING id"
        ),
        {"m": body.module, "f": json.dumps(filters), "c": list(channels), "s": subject, "b": message, "n": len(rows), "by": actor.id},
    ).scalar_one()
    queued = 0
    for r in rows:
        queued += queue_message(
            conn, r["name"], r["email"], r["phone"] or None, body.module, "staff_message", subject, message,
            channels=channels, sent_by=actor.id, batch_id=batch_id,
        )
    label = MODULE_LABELS[cast(Module, body.module)]
    write_audit(conn, actor, "message.bulk_sent", f"{label} · {len(rows)} clients · {', '.join(channels)} · {subject}")
    return {"batch_id": str(batch_id), "queued": queued}
