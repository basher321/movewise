"""The signed-in applicant's own applications (spec B05).

Another applicant's application is 404, never 403, so ids cannot be guessed.
"""

import json
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import (
    APPLY_LOCK,
    add_event,
    base_view,
    check_answers,
    event_view,
    fee_now,
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
from app.stages import AppModule

router = APIRouter()

_PUBLIC_ITEM = {
    "study": text("SELECT * FROM universities WHERE slug = :slug AND published"),
    "job": text("SELECT * FROM vacancies WHERE slug = :slug AND NOT closed AND employer_verified"),
    "visa": text("SELECT * FROM visa_programs WHERE slug = :slug AND published"),
}
_OPEN_FOR_ITEM = text(
    "SELECT * FROM applications WHERE applicant_id = :applicant AND status IN ('active', 'on_hold') "
    "AND COALESCE(university_id, vacancy_id, visa_program_id) = :item"
)
_INSERT_APP = text(
    "INSERT INTO applications (ref, module, applicant_id, university_id, vacancy_id, visa_program_id, answers) "
    "VALUES (:ref, :module, :applicant, :university, :vacancy, :visa, CAST(:answers AS jsonb)) RETURNING *"
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


class ApplyIn(BaseModel):
    item_slug: str = Field(max_length=200)
    answers: dict[str, Any] = Field(default_factory=dict)


def _app_module(module: str) -> AppModule:
    if module not in ("study", "job", "visa"):
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
    view["fee_poisha"] = None if app["fee_paid"] else fee_now(conn, module, item)
    if module == "study" and app["fee_paid"]:
        view["apply_link"] = item["apply_link"]
    if module in ("job", "visa"):  # visa: the biometrics / interview appointment
        view.update(interview_fields(app))
    view.update(documents_part(conn, [app], "applicant")[app["id"]])
    view["answers"] = app["answers"]
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
    answers = check_answers(app_module, body.answers)
    item = conn.execute(_PUBLIC_ITEM[app_module], {"slug": body.item_slug.strip()}).mappings().one_or_none()
    if item is None:
        what = {"study": "University", "job": "Vacancy", "visa": "Visa programme"}[app_module]
        raise ApiError("NOT_FOUND", 404, f"{what} not found.")

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
            "vacancy": item["id"] if app_module == "job" else None,
            "visa": item["id"] if app_module == "visa" else None,
            "answers": json.dumps(answers),
        },
    ).mappings().one()
    add_event(conn, app["id"], me.actor, "Application started")
    title = item_title(app_module, item)
    fee = fee_now(conn, app_module, item)
    notify_applicant(
        conn,
        app,
        "application_received",
        f"Application received - {app['ref']}",
        f"Thank you for applying to {title}. Your reference is {app['ref']}. "
        f"The application fee is {money_text(fee)}. You can pay it and follow every step in your profile.",
    )
    write_audit(conn, me.actor, "application.started", f"{app['ref']} · {title}")
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
