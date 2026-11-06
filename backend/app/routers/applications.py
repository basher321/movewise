"""The signed-in applicant's own applications (spec B05).

Another applicant's application is 404, never 403, so ids cannot be guessed.
"""

import json
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import (
    APPLY_LOCK,
    add_event,
    app_fee,
    base_view,
    check_answers,
    event_view,
    interview_fields,
    item_row,
    item_title,
    money_text,
    new_ref,
    not_found,
    notify_applicant,
    parse_id,
    public_item,
    stages_list,
)
from app.audit import write_audit
from app.auth.deps import Applicant, current_applicant
from app.db.engine import get_conn
from app.documents import documents_part
from app.errors import ApiError, parse_body
from app.stages import AppModule, stage_count, stage_name

router = APIRouter()

_PUBLIC_ITEM = {
    "study": text("SELECT * FROM universities WHERE slug = :slug AND published"),
    "job": text("SELECT * FROM vacancies WHERE slug = :slug AND NOT remote AND NOT closed AND employer_verified"),
    "remote": text("SELECT * FROM vacancies WHERE slug = :slug AND remote AND NOT closed AND employer_verified"),
    "visa": text("SELECT * FROM visa_programs WHERE slug = :slug AND published"),
}
_OPEN_FOR_ITEM = text(
    "SELECT * FROM applications WHERE applicant_id = :applicant AND status IN ('active', 'on_hold') "
    "AND COALESCE(university_id, vacancy_id, visa_program_id) = :item"
)
_INSERT_APP = text(
    "INSERT INTO applications (ref, module, applicant_id, university_id, vacancy_id, visa_program_id, answers, self_apply) "
    "VALUES (:ref, :module, :applicant, :university, :vacancy, :visa, CAST(:answers AS jsonb), :self_apply) RETURNING *"
)
_MY_APPS = text(
    "SELECT a.*, COALESCE(u.name, v.title, vp.title) AS item_title, "
    "COALESCE(u.country, v.country, vp.country) AS item_country, "
    "COALESCE(u.slug, v.slug, vp.slug) AS item_slug, v.employer AS item_employer "
    "FROM applications a LEFT JOIN universities u ON u.id = a.university_id "
    "LEFT JOIN vacancies v ON v.id = a.vacancy_id "
    "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id "
    "WHERE a.applicant_id = :applicant AND a.module = :module ORDER BY a.created_at DESC, a.id"
)
_MY_APP = text("SELECT * FROM applications WHERE id = :id AND applicant_id = :applicant AND module = :module")
_MY_APP_LOCKED = text(
    "SELECT * FROM applications WHERE id = :id AND applicant_id = :applicant AND module = :module FOR UPDATE"
)
_PUBLIC_EVENTS = text(
    "SELECT * FROM app_events WHERE application_id = :id AND public ORDER BY at DESC, id DESC"
)
_ADVISOR = text("SELECT name, active FROM admin_users WHERE id = :id")
# The applicant submits the required documents together; the latest submission is an event.
DOCS_SUBMITTED = "Documents submitted"
DOCS_RESUBMITTED = "Documents resubmitted"
_DOCS_SUBMITTED_AT = text(
    "SELECT max(at) FROM app_events WHERE application_id = :id AND by_kind = 'applicant' "
    "AND text IN ('Documents submitted', 'Documents resubmitted')"
)
_NEWEST_UPLOAD = text(
    "SELECT max(uploaded_at) FROM documents WHERE application_id = :id AND status <> 'replaced'"
)


class ApplyIn(BaseModel):
    item_slug: str = Field(max_length=200)
    answers: dict[str, Any] = Field(default_factory=dict)
    # Self Apply (universities only): pay the self-apply fee, then get the official link.
    self_apply: StrictBool = False


def _app_module(module: str) -> AppModule:
    if module not in ("study", "job", "visa", "remote"):
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return cast(AppModule, module)


def _own(conn: Connection, me: Applicant, module: AppModule, app_id: str, lock: bool = False) -> RowMapping:
    sql = _MY_APP_LOCKED if lock else _MY_APP
    row = conn.execute(sql, {"id": parse_id(app_id), "applicant": me.account["id"], "module": module}).mappings().one_or_none()
    if row is None:
        raise not_found()
    return row


def _detail(conn: Connection, app: RowMapping) -> dict[str, Any]:
    module: AppModule = app["module"]
    item = item_row(conn, app)
    view = base_view(app)
    view["item"] = public_item(conn, module, item)
    view["item_title"] = item_title(module, item)
    view["stages"] = stages_list(module)
    view["history"] = [event_view(e) for e in conn.execute(_PUBLIC_EVENTS, {"id": app["id"]}).mappings()]
    advisor = conn.execute(_ADVISOR, {"id": app["assigned_to"]}).one_or_none() if app["assigned_to"] else None
    view["advisor_name"] = advisor.name if advisor and advisor.active else None
    view["fee_poisha"] = None if app["fee_paid"] else app_fee(conn, app, item)
    if module == "study" and app["fee_paid"]:
        view["apply_link"] = item["apply_link"]
    if module in ("job", "visa", "remote"):  # visa: the biometrics / interview appointment
        view.update(interview_fields(app))
    view.update(documents_part(conn, [app], "applicant")[app["id"]])
    view["answers"] = app["answers"]
    submitted = conn.execute(_DOCS_SUBMITTED_AT, {"id": app["id"]}).scalar_one_or_none()
    view["documents_submitted_at"] = submitted.isoformat() if submitted else None
    view.update(_payment_part(conn, app["id"]))
    # B20: the completion letter, once staff issued it (valid while the case is completed).
    letter = conn.execute(
        text("SELECT letter_id, issued_at FROM case_letters WHERE application_id = :id"), {"id": app["id"]}
    ).one_or_none()
    view["letter"] = (
        None
        if letter is None
        else {"id": letter.letter_id, "issued_at": letter.issued_at.isoformat(), "valid": app["status"] == "completed"}
    )
    return view


_LATEST_PAYMENT = text(
    "SELECT * FROM payments WHERE ref_type = 'application' AND ref_id = :id ORDER BY created_at DESC, id LIMIT 1"
)
_INVOICE_OF_APP = text(
    "SELECT i.* FROM invoices i JOIN payments p ON p.id = i.payment_id "
    "WHERE p.ref_type = 'application' AND p.ref_id = :id ORDER BY i.issued_at DESC LIMIT 1"
)


def _payment_part(conn: Connection, app_id: Any) -> dict[str, Any]:
    """B07: the latest fee payment and the invoice, for the applicant's own page."""
    from app.payments.invoices import invoice_view  # payments imports this module's helpers

    pay = conn.execute(_LATEST_PAYMENT, {"id": app_id}).mappings().one_or_none()
    invoice = conn.execute(_INVOICE_OF_APP, {"id": app_id}).mappings().one_or_none()
    email_status = None
    if invoice is not None:
        email_status = conn.execute(
            text(
                "SELECT status FROM notifications WHERE event = 'payment_received' AND channel = 'email' "
                "AND subject = :s ORDER BY at DESC LIMIT 1"
            ),
            {"s": f"Payment received - {invoice['no']}"},
        ).scalar_one_or_none() or "none"
    return {
        "payment": None
        if pay is None
        else {
            "id": str(pay["id"]),
            "status": pay["status"],
            "method": pay["method"],
            "amount_poisha": int(pay["amount_poisha"]),
            "manual_ref": pay["manual_ref"],
            "note": pay["decision_note"],
            "created_at": pay["created_at"].isoformat(),
            "paid_at": pay["paid_at"].isoformat() if pay["paid_at"] else None,
        },
        "invoice": None if invoice is None else invoice_view(invoice, email_status),
    }


@router.post("/me/{module}/applications")
async def apply(
    module: str, request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app_module = _app_module(module)
    body = parse_body(ApplyIn, await request.body())
    # The advisory lock below can wait for a parallel request of the same applicant. Waiting in a
    # worker thread keeps the event loop free, so that other request can finish and release it.
    return await run_in_threadpool(_start_application, conn, me, app_module, body)


def _start_application(conn: Connection, me: Applicant, app_module: AppModule, body: ApplyIn) -> dict[str, Any]:
    answers = check_answers(app_module, body.answers)
    item = conn.execute(_PUBLIC_ITEM[app_module], {"slug": body.item_slug.strip()}).mappings().one_or_none()
    if item is None:
        what = {"study": "University", "job": "Vacancy", "visa": "Visa programme", "remote": "Remote job"}[app_module]
        raise ApiError("NOT_FOUND", 404, f"{what} not found.")
    if body.self_apply and (app_module != "study" or item["self_apply_fee_poisha"] is None):
        raise ApiError("CONFLICT", 409, "Self Apply is not available for this university yet.")

    applicant_id = me.account["id"]
    conn.execute(text("SELECT pg_advisory_xact_lock(:a, hashtext(:b))"), {"a": APPLY_LOCK, "b": str(applicant_id)})
    existing = conn.execute(_OPEN_FOR_ITEM, {"applicant": applicant_id, "item": item["id"]}).mappings().one_or_none()
    if existing is not None:
        return _detail(conn, existing)

    app = conn.execute(
        _INSERT_APP,
        {
            "ref": new_ref(conn),
            "module": app_module,
            "applicant": applicant_id,
            "university": item["id"] if app_module == "study" else None,
            "vacancy": item["id"] if app_module in ("job", "remote") else None,
            "visa": item["id"] if app_module == "visa" else None,
            "answers": json.dumps(answers),
            "self_apply": body.self_apply,
        },
    ).mappings().one()
    add_event(conn, app["id"], me.actor, "Self Apply started" if body.self_apply else "Application started")
    title = item_title(app_module, item)
    fee = app_fee(conn, app, item) or 0
    if body.self_apply:
        message = (
            f"Thank you for choosing Self Apply for {title}. Your reference is {app['ref']}. "
            f"Pay the self-apply fee of {money_text(fee)} in your profile to get the official application link."
        )
    else:
        message = (
            f"Thank you for applying to {title}. Your reference is {app['ref']}. "
            f"The application fee is {money_text(fee)}. You can pay it and follow every step in your profile."
        )
    notify_applicant(conn, app, "application_received", f"Application received - {app['ref']}", message)
    write_audit(
        conn, me.actor, "application.self_apply_started" if body.self_apply else "application.started", f"{app['ref']} · {title}"
    )
    return _detail(conn, app)


@router.get("/me/{module}/applications")
def my_applications(
    module: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    app_module = _app_module(module)
    rows = conn.execute(_MY_APPS, {"applicant": me.account["id"], "module": app_module}).mappings()
    return [
        {
            **base_view(r),
            "item_title": r["item_title"],
            "item_country": r["item_country"],
            "item_slug": r["item_slug"],
            "item_employer": r["item_employer"],
        }
        for r in rows
    ]


@router.get("/me/{module}/applications/{app_id}")
def my_application(
    module: str, app_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _detail(conn, _own(conn, me, _app_module(module), app_id))


@router.post("/me/{module}/applications/{app_id}/documents/submit")
def submit_documents(
    module: str, app_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    """Send every required document to review in one step. While the case is still at its first
    stage it moves on to the next processing stage."""
    app_module = _app_module(module)
    app = _own(conn, me, app_module, app_id, lock=True)
    if app["self_apply"]:
        raise ApiError("CONFLICT", 409, "A Self Apply has no documents to submit.")
    if app["status"] != "active":
        raise ApiError("CONFLICT", 409, "Documents can only be submitted while the application is active.")
    missing = documents_part(conn, [app], "applicant")[app["id"]]["missing_count"]
    if missing:
        raise ApiError(
            "VALIDATION",
            422,
            f"Please upload every required document first ({missing} still needed).",
        )
    submitted = conn.execute(_DOCS_SUBMITTED_AT, {"id": app["id"]}).scalar_one_or_none()
    newest = conn.execute(_NEWEST_UPLOAD, {"id": app["id"]}).scalar_one_or_none()
    if submitted is not None and (newest is None or newest <= submitted):
        raise ApiError("CONFLICT", 409, "Your documents are already submitted.")

    add_event(conn, app["id"], me.actor, DOCS_RESUBMITTED if submitted else DOCS_SUBMITTED)
    if app["stage"] == 0 and stage_count(app_module) > 1:
        conn.execute(text("UPDATE applications SET stage = 1 WHERE id = :id"), {"id": app["id"]})
        add_event(conn, app["id"], me.actor, f"Stage -> {stage_name(app_module, 1)}")
    write_audit(conn, me.actor, "documents.submitted", app["ref"])
    return _detail(conn, _own(conn, me, app_module, app_id))


@router.post("/me/{module}/applications/{app_id}/withdraw")
def withdraw(
    module: str, app_id: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _own(conn, me, _app_module(module), app_id, lock=True)
    if app["status"] not in ("active", "on_hold"):
        raise ApiError("CONFLICT", 409, "Only an active or on-hold application can be withdrawn.")
    updated = conn.execute(
        text("UPDATE applications SET status = 'withdrawn' WHERE id = :id RETURNING *"), {"id": app["id"]}
    ).mappings().one()
    add_event(conn, app["id"], me.actor, "Withdrawn by applicant")
    write_audit(conn, me.actor, "application.withdrawn", app["ref"])
    return _detail(conn, updated)
