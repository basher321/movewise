"""Admin case handling (spec B05): applications of a section, stage, status, assignment,
deadline, interview and offer, internal notes, case emails, and applicant accounts.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Every change locks the application row and writes exactly one audit row.
"""

import secrets
from datetime import date, datetime
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import (
    STATUS_LABELS,
    add_event,
    base_view,
    dhaka_text,
    event_view,
    interview_fields,
    item_row,
    item_title,
    not_found,
    notify_applicant,
    parse_id,
    PROVIDER_LABEL,
    provider_email,
    stages_list,
)
from app.audit import Actor, write_audit
from app.auth.deps import ensure_section, get_current_actor
from app.auth.passwords import hash_password
from app.auth.sessions import end_applicant_sessions
from app.db.engine import get_conn
from app.documents import documents_part
from app.errors import ApiError, parse_body
from app.licence import DHAKA, MODULES, Module
from app.notify.outbox import queue_message
from app.stages import AppModule, stage_count, stage_name

router = APIRouter()

PAGE_SIZE = 50
MAX_NOTE = 5000
MAX_SUBJECT = 200
MAX_BODY = 10_000

ADMIN_STATUSES = ("active", "on_hold", "rejected", "completed")


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _module_param(module: str | None) -> AppModule:
    if module not in ("study", "job", "visa"):
        raise _invalid("Please choose a module: study, job or visa.")
    return cast(AppModule, module)


# ---------------------------------------------------------------- views

_SELECT = (
    "SELECT a.*, p.public_id AS p_public_id, p.name AS p_name, p.email AS p_email, p.phone AS p_phone, "
    "COALESCE(u.name, v.title, vp.title) AS item_title, v.employer AS item_employer, "
    "COALESCE(u.country, v.country, vp.country) AS item_country, COALESCE(u.slug, v.slug, vp.slug) AS item_slug, "
    "COALESCE(u.admissions_email, v.employer_email, vp.embassy_email) AS provider_email, "
    "s.name AS assigned_name, s.active AS assigned_active, "
    "g.name AS agent_name, g.active AS agent_active "
    "FROM applications a "
    "JOIN applicant_accounts p ON p.id = a.applicant_id "
    "LEFT JOIN universities u ON u.id = a.university_id "
    "LEFT JOIN vacancies v ON v.id = a.vacancy_id "
    "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id "
    "LEFT JOIN admin_users s ON s.id = a.assigned_to "
    "LEFT JOIN partner_agents g ON g.id = a.agent_id "
)
_EVENTS = text(
    "SELECT * FROM app_events WHERE application_id IN :ids ORDER BY at DESC, id DESC"
).bindparams(bindparam("ids", expanding=True))
_EMAILS = text(
    "SELECT id, application_id, at, channel, to_address, subject, status FROM notifications "
    "WHERE application_id IN :ids ORDER BY at DESC, id DESC"
).bindparams(bindparam("ids", expanding=True))


def _rows_view(conn: Connection, rows: list[RowMapping]) -> list[dict[str, Any]]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    events: dict[Any, list[dict[str, Any]]] = {i: [] for i in ids}
    for e in conn.execute(_EVENTS, {"ids": ids}).mappings():
        events[e["application_id"]].append(event_view(e))
    emails: dict[Any, list[dict[str, Any]]] = {i: [] for i in ids}
    for n in conn.execute(_EMAILS, {"ids": ids}).mappings():
        emails[n["application_id"]].append(
            {
                "id": str(n["id"]),
                "at": n["at"].isoformat(),
                "channel": n["channel"],
                "to": n["to_address"],
                "subject": n["subject"],
                "status": n["status"],
            }
        )
    docs = documents_part(conn, rows, "admin")
    out = []
    for r in rows:
        module: AppModule = r["module"]
        view = base_view(r)
        view.update(interview_fields(r))
        view["stages"] = stages_list(module)
        view["applicant"] = {
            "id": str(r["applicant_id"]),
            "public_id": r["p_public_id"],
            "name": r["p_name"],
            "email": r["p_email"],
            "phone": r["p_phone"],
        }
        view["item"] = {
            "title": r["item_title"],
            "employer": r["item_employer"],
            "country": r["item_country"],
            "slug": r["item_slug"],
        }
        view["provider_email"] = r["provider_email"] or ""
        view["answers"] = r["answers"]
        if r["assigned_to"] is None:
            view["assigned_to"] = None
        else:
            name = r["assigned_name"] if r["assigned_active"] else f"{r['assigned_name']} (deactivated)"
            view["assigned_to"] = {"id": str(r["assigned_to"]), "name": name, "active": r["assigned_active"]}
        # B16: the partner agent who referred this case, or None for a direct case.
        if r["agent_id"] is None:
            view["agent"] = None
        else:
            view["agent"] = {"id": str(r["agent_id"]), "name": r["agent_name"], "active": r["agent_active"]}
        view["history"] = events[r["id"]]
        view["emails"] = emails[r["id"]]
        view.update(docs[r["id"]])
        out.append(view)
    return out


def _one_view(conn: Connection, app_id: Any) -> dict[str, Any]:
    row = conn.execute(text(_SELECT + "WHERE a.id = :id"), {"id": app_id}).mappings().one()
    return _rows_view(conn, [row])[0]


def _load(conn: Connection, actor: Actor, app_id: str, lock: bool) -> RowMapping:
    """The application, after the section check. Locked when it will change."""
    uid = parse_id(app_id)
    module = conn.execute(text("SELECT module FROM applications WHERE id = :id"), {"id": uid}).scalar_one_or_none()
    if module is None:
        raise not_found()
    ensure_section(conn, actor, module)
    sql = "SELECT * FROM applications WHERE id = :id" + (" FOR UPDATE" if lock else "")
    return conn.execute(text(sql), {"id": uid}).mappings().one()


# ---------------------------------------------------------------- list and read


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/admin/applications")
def list_applications(
    module: str | None = None,
    q: str = "",
    status: str = "",
    assigned: str = "",
    page: int = 1,
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    app_module = _module_param(module)
    ensure_section(conn, actor, app_module)
    where = ["a.module = :module"]
    params: dict[str, Any] = {"module": app_module}
    if status:
        if status not in STATUS_LABELS:
            raise _invalid("Unknown status.")
        where.append("a.status = :status")
        params["status"] = status
    if assigned == "me":
        where.append("a.assigned_to = :assigned")
        params["assigned"] = actor.id
    elif assigned == "none":
        where.append("a.assigned_to IS NULL")
    elif assigned:
        try:
            params["assigned"] = UUID(assigned)
        except ValueError:
            raise _invalid("Unknown admin.") from None
        where.append("a.assigned_to = :assigned")
    search = q.strip()[:100]
    if search:
        where.append(
            "(a.ref ILIKE :q OR p.name ILIKE :q OR p.email ILIKE :q OR p.public_id ILIKE :q "
            "OR p.phone ILIKE :q OR COALESCE(u.name, v.title, vp.title) ILIKE :q OR COALESCE(v.employer, '') ILIKE :q)"
        )
        params["q"] = _like(search)
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    clause = " WHERE " + " AND ".join(where)
    count_sql = (
        "SELECT count(*) FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id "
        "LEFT JOIN universities u ON u.id = a.university_id LEFT JOIN vacancies v ON v.id = a.vacancy_id "
        "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id"
        + clause
    )
    total = int(conn.execute(text(count_sql), params).scalar_one())
    rows = list(
        conn.execute(
            text(_SELECT + clause + " ORDER BY a.updated_at DESC, a.id LIMIT :limit OFFSET :offset"),
            {**params, "limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE},
        ).mappings()
    )
    return {"items": _rows_view(conn, rows), "total": total, "page": page, "page_size": PAGE_SIZE}


@router.get("/admin/applications/{app_id}")
def get_application(
    app_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=False)
    return _one_view(conn, app["id"])


# ---------------------------------------------------------------- stage and status


class StageIn(BaseModel):
    stage: StrictInt
    note: str = Field(default="", max_length=MAX_NOTE)
    notify: StrictBool = True


class StatusIn(BaseModel):
    status: str = Field(max_length=40)
    reason: str = Field(default="", max_length=MAX_NOTE)


@router.post("/admin/applications/{app_id}/stage")
async def set_stage(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    body = parse_body(StageIn, await request.body())
    module: AppModule = app["module"]
    if not 0 <= body.stage < stage_count(module):
        raise _invalid(f"Stage must be from 0 to {stage_count(module) - 1}.")
    if app["status"] != "active":
        raise ApiError("CONFLICT", 409, "The stage can only change while the application is active.")
    last = body.stage == stage_count(module) - 1
    new_status = "completed" if last else app["status"]
    conn.execute(
        text("UPDATE applications SET stage = :stage, status = :status WHERE id = :id"),
        {"stage": body.stage, "status": new_status, "id": app["id"]},
    )
    name = stage_name(module, body.stage)
    note = body.note.strip()
    add_event(conn, app["id"], actor, f"Stage -> {name}", note)
    if body.notify:
        message = f"Your application {app['ref']} has moved to: {name}."
        if note:
            message += f"\n\n{note}"
        notify_applicant(conn, app, "stage_changed", f"Update on {app['ref']}: {name}", message)
    write_audit(conn, actor, "application.stage", f"{app['ref']} -> {name}")
    return _one_view(conn, app["id"])


@router.post("/admin/applications/{app_id}/status")
async def set_status(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    body = parse_body(StatusIn, await request.body())
    reason = body.reason.strip()
    if body.status == "withdrawn":
        raise _invalid("Only the applicant can withdraw an application.")
    if body.status not in ADMIN_STATUSES:
        raise _invalid("Please choose a status.")
    current = app["status"]
    if current == "withdrawn":
        raise ApiError("CONFLICT", 409, "A withdrawn application cannot be reopened.")
    if body.status == current:
        raise ApiError("CONFLICT", 409, f"The application is already {STATUS_LABELS[current].lower()}.")
    if body.status in ("on_hold", "rejected") and not reason:
        raise _invalid("Please give a reason.")
    if body.status == "active" and current in ("rejected", "completed") and not reason:
        raise _invalid("Please give a reason for reopening.")
    if body.status == "active" and current in ("rejected", "completed"):
        clash = conn.execute(
            text(
                "SELECT 1 FROM applications WHERE applicant_id = :p AND id <> :id AND status IN ('active', 'on_hold') "
                "AND COALESCE(university_id, vacancy_id, visa_program_id) = COALESCE(:u, :v, :vp)"
            ),
            {
                "p": app["applicant_id"],
                "id": app["id"],
                "u": app["university_id"],
                "v": app["vacancy_id"],
                "vp": app["visa_program_id"],
            },
        ).first()
        if clash is not None:
            raise ApiError("CONFLICT", 409, "This applicant already has an open application for the same item.")
    conn.execute(text("UPDATE applications SET status = :s WHERE id = :id"), {"s": body.status, "id": app["id"]})
    label = STATUS_LABELS[body.status]
    add_event(conn, app["id"], actor, f"Status -> {label}", reason)
    message = f"The status of your application {app['ref']} is now: {label}."
    if reason:
        message += f"\n\nReason: {reason}"
    notify_applicant(conn, app, "status_changed", f"Update on {app['ref']}: {label}", message)
    write_audit(conn, actor, "application.status", f"{app['ref']} -> {body.status}")
    return _one_view(conn, app["id"])


# ---------------------------------------------------------------- case fields


class PatchIn(BaseModel):
    assigned_to: str | None = None
    deadline: date | None = None
    interview_at: datetime | None = None
    interview_result: Literal["pending", "passed", "failed"] = "pending"
    offered_salary_usd: StrictInt | None = None


def _check_assignee(conn: Connection, module: AppModule, value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        uid = UUID(value)
    except ValueError:
        raise _invalid("Please choose an admin of this section.") from None
    row = conn.execute(
        text("SELECT role, approved, active, sections FROM admin_users WHERE id = :id"), {"id": uid}
    ).one_or_none()
    ok = (
        row is not None
        and row.approved
        and row.active
        and (row.role == "super_admin" or (row.role == "admin" and module in row.sections))
    )
    if not ok:
        raise _invalid("Please choose an admin of this section.")
    return uid


_FIELD_LABELS = {
    "assigned_to": "assigned to",
    "deadline": "deadline",
    "interview_at": "interview",
    "interview_result": "interview result",
    "offered_salary_usd": "offered salary",
}


@router.patch("/admin/applications/{app_id}")
async def patch_application(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    body = parse_body(PatchIn, await request.body())
    module: AppModule = app["module"]
    sent = body.model_fields_set
    values: dict[str, Any] = {}
    if "assigned_to" in sent:
        values["assigned_to"] = _check_assignee(conn, module, body.assigned_to)
    if "deadline" in sent:
        values["deadline"] = body.deadline
    if "interview_at" in sent:
        at = body.interview_at
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=DHAKA)  # a time without a zone is Dhaka time
        values["interview_at"] = at
    if "interview_result" in sent:
        values["interview_result"] = body.interview_result
    if "offered_salary_usd" in sent:
        if body.offered_salary_usd is not None and body.offered_salary_usd <= 0:
            raise _invalid("Offered salary must be above 0.")
        values["offered_salary_usd"] = body.offered_salary_usd
    changed = [k for k, v in values.items() if app[k] != v]
    if changed:
        sets = ", ".join(f"{k} = :{k}" for k in changed)
        conn.execute(text(f"UPDATE applications SET {sets} WHERE id = :id"), {**{k: values[k] for k in changed}, "id": app["id"]})
        labels = ", ".join(_FIELD_LABELS[k] for k in changed)
        add_event(conn, app["id"], actor, f"Case updated: {labels}", public=False)
        if "interview_at" in changed and values["interview_at"] is not None:
            notify_applicant(
                conn,
                app,
                "interview_scheduled",
                f"Interview scheduled - {app['ref']}",
                f"Your interview for application {app['ref']} is on {dhaka_text(values['interview_at'])}.",
            )
        write_audit(conn, actor, "application.updated", f"{app['ref']}: {labels}")
    return {**_one_view(conn, app["id"]), "changed": changed}


# ---------------------------------------------------------------- notes and emails


class NoteIn(BaseModel):
    note: str = Field(max_length=MAX_NOTE)


class EmailIn(BaseModel):
    to: Literal["applicant", "provider"]
    subject: str = Field(max_length=1000)
    body: str = Field(max_length=MAX_BODY)


@router.post("/admin/applications/{app_id}/notes")
async def add_note(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    note = parse_body(NoteIn, await request.body()).note.strip()
    if not note:
        raise _invalid("Please write the note.")
    add_event(conn, app["id"], actor, "Internal note", note, public=False)
    write_audit(conn, actor, "application.note", app["ref"])
    return _one_view(conn, app["id"])


@router.post("/admin/applications/{app_id}/email")
async def send_case_email(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    body = parse_body(EmailIn, await request.body())
    subject, message = body.subject.strip(), body.body.strip()
    if not subject or not message:
        raise _invalid("Please write the subject and the message.")
    if len(subject) > MAX_SUBJECT:
        raise _invalid(f"Subject must be at most {MAX_SUBJECT} characters.")
    module: AppModule = app["module"]
    if body.to == "applicant":
        notify_applicant(conn, app, "case_email", subject, message)
        who = "applicant"
    else:
        item = item_row(conn, app)
        address = provider_email(module, item)
        if not address:
            raise _invalid(f"No email on file for the {PROVIDER_LABEL[module]}.")
        name = item["employer"] if module == "job" else item_title(module, item)
        queue_message(conn, name, address, None, module, "case_email", subject, message, app["id"])
        who = PROVIDER_LABEL[module]
    add_event(conn, app["id"], actor, f"Email sent to {who}: {subject}", public=False)
    write_audit(conn, actor, "application.email", f"{app['ref']} -> {who}")
    return _one_view(conn, app["id"])


# ---------------------------------------------------------------- applicant accounts

_ACCOUNTS = text(
    "SELECT id, public_id, username, name, email, phone, country, education, email_verified, created_at "
    "FROM applicant_accounts WHERE module = :module ORDER BY created_at DESC, id LIMIT 2000"
)


@router.get("/admin/accounts")
def list_accounts(
    module: str | None = None, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    if module not in MODULES:
        raise _invalid("Please choose a module.")
    ensure_section(conn, actor, cast(Module, module))
    return [
        {
            "id": str(r["id"]),
            "public_id": r["public_id"],
            "username": r["username"],
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "country": r["country"],
            "education": r["education"],
            "email_verified": r["email_verified"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in conn.execute(_ACCOUNTS, {"module": module}).mappings()
    ]


# ---------------------------------------------------------------- forgotten passwords

TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


@router.post("/admin/accounts/{account_id}/reset-password")
def reset_applicant_password(
    account_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, str]:
    """Owner decision (2026-11-01): no email codes. A person who forgot their password asks the
    office; staff of that section set a temporary password and tell it to them. All their other
    sessions end. The temporary password is shown once and never stored in plain text."""
    try:
        uid = UUID(account_id)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, "Account not found.") from None
    row = conn.execute(
        text("SELECT id, module, public_id, username FROM applicant_accounts WHERE id = :id FOR UPDATE"), {"id": uid}
    ).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Account not found.")
    ensure_section(conn, actor, row["module"])
    temporary = "".join(secrets.choice(TEMP_ALPHABET) for _ in range(10))
    conn.execute(
        text("UPDATE applicant_accounts SET password_hash = :h WHERE id = :id"), {"h": hash_password(temporary), "id": uid}
    )
    end_applicant_sessions(conn, uid)
    write_audit(conn, actor, "applicant.password_reset_by_staff", row["public_id"])
    return {"temporary_password": temporary, "username": row["username"] or ""}
