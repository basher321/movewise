"""Custom payments (spec B27): payments of any amount on a case or a course enrolment, on top of
the normal fee. Staff ask for one (a payment request), or the applicant pays an amount of their
own. Each is paid through the shared payment service (B07) with ref_type 'request'.
Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Every change writes exactly one audit row in the same transaction.
"""

import secrets
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import add_event, item_row, item_title
from app.audit import Actor, write_audit
from app.auth.deps import Applicant, client_ip, current_applicant, ensure_section, get_current_actor
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULES, Module
from app.stages import AppModule
from app.payments.service import (
    bkash_status,
    eps_status,
    money_text,
    notify_person,
    record_end,
    register_on_ended,
    register_on_paid,
)
from app.routers.pay import PayIn, start_payment

router = APIRouter()

MIN_POISHA = 100 * 100  # 100 taka
MAX_POISHA = 1_000_000 * 100  # 10,00,000 taka
MAX_DESCRIPTION = 200
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# A started online payment nobody came back from: after this long it no longer blocks a cancel.
STALE_START = "1 hour"


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _not_found() -> ApiError:
    return ApiError("NOT_FOUND", 404, "Payment request not found.")


def _module(value: str | None) -> Module:
    if value not in MODULES:
        raise _invalid("Please choose a service: course, study, job, visa or remote.")
    return cast(Module, value)


def _uuid(value: str, error: ApiError) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise error from None


def check_amount(value: int) -> int:
    if value < MIN_POISHA or value > MAX_POISHA:
        raise _invalid(f"The amount must be between {money_text(MIN_POISHA)} and {money_text(MAX_POISHA)}.")
    if value % 100:
        raise _invalid("The amount must be a whole number of taka.")
    return value


def _description(value: str, label: str) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) > MAX_DESCRIPTION:
        raise _invalid(f"{label} must be at most {MAX_DESCRIPTION} characters.")
    return cleaned


def _new_ref(conn: Connection) -> str:
    exists = text("SELECT 1 FROM payment_requests WHERE ref = :r")
    while True:
        ref = "PR-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
        if conn.execute(exists, {"r": ref}).first() is None:
            return ref


# ---------------------------------------------------------------- the case a request belongs to


def _case(conn: Connection, module: Module, case_id: UUID, applicant_id: Any = None, lock: bool = False) -> dict[str, Any]:
    """The course enrolment or application, as {id, ref, title, applicant_id, open}. NOT_FOUND
    when it does not exist, is in another service, or (with applicant_id) is someone else's."""
    suffix = " FOR UPDATE" if lock else ""
    if module == "course":
        row = conn.execute(
            text(
                "SELECT e.id, e.order_no, e.applicant_id, e.status, c.title FROM enrolments e "
                "JOIN courses c ON c.id = e.course_id WHERE e.id = :id" + (" FOR UPDATE OF e" if lock else "")
            ),
            {"id": case_id},
        ).mappings().one_or_none()
        if row is None or (applicant_id is not None and row["applicant_id"] != applicant_id):
            raise ApiError("NOT_FOUND", 404, "Course enrolment not found.")
        return {
            "id": row["id"], "ref": row["order_no"], "title": row["title"], "applicant_id": row["applicant_id"],
            "application_id": None, "enrolment_id": row["id"], "open": row["status"] != "cancelled",
        }
    app = conn.execute(
        text("SELECT * FROM applications WHERE id = :id AND module = :m" + suffix), {"id": case_id, "m": module}
    ).mappings().one_or_none()
    if app is None or (applicant_id is not None and app["applicant_id"] != applicant_id):
        raise ApiError("NOT_FOUND", 404, "Application not found.")
    return {
        "id": app["id"], "ref": app["ref"], "title": item_title(cast(AppModule, module), item_row(conn, app)),
        "applicant_id": app["applicant_id"], "application_id": app["id"], "enrolment_id": None,
        "open": app["status"] in ("active", "on_hold"),
    }


def _ensure_open(case: dict[str, Any]) -> None:
    if not case["open"]:
        raise ApiError("CONFLICT", 409, "This case is closed, so no payment can be added to it.")


# ---------------------------------------------------------------- views

_SELECT = (
    "SELECT r.*, COALESCE(a.ref, e.order_no) AS case_ref, "
    "(SELECT row_to_json(x) FROM (SELECT p.id, p.status, p.method FROM payments p "
    "  WHERE p.ref_type = 'request' AND p.ref_id = r.id ORDER BY p.created_at DESC, p.id LIMIT 1) x) AS last_payment, "
    "(SELECT i.no FROM invoices i JOIN payments p ON p.id = i.payment_id "
    "  WHERE p.ref_type = 'request' AND p.ref_id = r.id ORDER BY i.issued_at DESC LIMIT 1) AS invoice_no "
    "FROM payment_requests r "
    "LEFT JOIN applications a ON a.id = r.application_id "
    "LEFT JOIN enrolments e ON e.id = r.enrolment_id "
)


def request_view(row: RowMapping) -> dict[str, Any]:
    last = row["last_payment"]
    return {
        "id": str(row["id"]),
        "ref": row["ref"],
        "module": row["module"],
        "case_id": str(row["application_id"] or row["enrolment_id"]),
        "case_ref": row["case_ref"],
        "kind": row["kind"],
        "description": row["description"],
        "amount_poisha": int(row["amount_poisha"]),
        "status": row["status"],
        "payment": None if not last else {"id": str(last["id"]), "status": last["status"], "method": last["method"]},
        "invoice_no": row["invoice_no"],
        "created_at": row["created_at"].isoformat(),
        "paid_at": row["paid_at"].isoformat() if row["paid_at"] else None,
    }


def _one(conn: Connection, request_id: Any) -> dict[str, Any]:
    return request_view(conn.execute(text(_SELECT + "WHERE r.id = :id"), {"id": request_id}).mappings().one())


def _purpose(row: RowMapping | dict[str, Any], case: dict[str, Any]) -> str:
    return f"{row['description']} - {case['title']} ({case['ref']}) · {row['ref']}"


# ---------------------------------------------------------------- payment hooks


def _request_paid(conn: Connection, payment: RowMapping) -> None:
    row = conn.execute(
        text(
            "UPDATE payment_requests SET status = 'paid', paid_at = now(), cancelled_at = NULL "
            "WHERE id = :id RETURNING *"
        ),
        {"id": payment["ref_id"]},
    ).mappings().one()
    if row["application_id"] is not None:
        add_event(
            conn, row["application_id"], None,
            f"Custom payment received ({money_text(payment['amount_poisha'])}, {row['ref']})",
        )


def _request_ended(conn: Connection, payment: RowMapping) -> None:
    """An own-amount request whose payment ended without money is closed: the applicant simply
    starts a new one. A staff request stays open so it can be paid again."""
    conn.execute(
        text(
            "UPDATE payment_requests SET status = 'cancelled', cancelled_at = now() "
            "WHERE id = :id AND kind = 'own' AND status = 'open' AND NOT EXISTS ("
            "  SELECT 1 FROM payments p WHERE p.ref_type = 'request' AND p.ref_id = :id "
            "  AND p.status IN ('initiated', 'pending_verify', 'paid'))"
        ),
        {"id": payment["ref_id"]},
    )


register_on_paid("request", _request_paid)
register_on_ended("request", _request_ended)


def _settle_started(conn: Connection, request_id: Any) -> RowMapping | None:
    """The live payment of a request, after asking the gateway about a started one. A start
    nobody came back from for over an hour is closed as abandoned."""
    live = conn.execute(
        text(
            "SELECT * FROM payments WHERE ref_type = 'request' AND ref_id = :id "
            "AND status IN ('initiated', 'pending_verify') FOR UPDATE"
        ),
        {"id": request_id},
    ).mappings().one_or_none()
    if live is None or live["status"] != "initiated":
        return live
    if live["method"] == "bkash":
        live = bkash_status(conn, live)
    elif live["method"] == "eps":
        live = eps_status(conn, live)
    if live["status"] != "initiated":
        return None if live["status"] not in ("pending_verify", "paid") else live
    stale = conn.execute(
        text(f"SELECT now() - created_at > interval '{STALE_START}' FROM payments WHERE id = :id"), {"id": live["id"]}
    ).scalar_one()
    if stale:
        record_end(conn, live["id"], "abandoned", "abandoned", {"reason": "payment request cancelled by staff"})
        return None
    return live


# ---------------------------------------------------------------- staff


class RequestIn(BaseModel):
    module: str = Field(max_length=20)
    case_id: str = Field(max_length=60)
    description: str = Field(max_length=1000)
    amount_poisha: StrictInt


@router.get("/admin/payment-requests")
def list_requests(
    module: str | None = None,
    case_id: str = "",
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    service = _module(module)
    ensure_section(conn, actor, service)
    params: dict[str, Any] = {"m": service}
    where = "WHERE r.module = :m "
    if case_id:
        params["c"] = _uuid(case_id, ApiError("NOT_FOUND", 404, "Case not found."))
        where += "AND (r.application_id = :c OR r.enrolment_id = :c) "
    rows = conn.execute(text(_SELECT + where + "ORDER BY r.created_at DESC, r.id LIMIT 200"), params).mappings()
    return {"items": [request_view(r) for r in rows]}


@router.post("/admin/payment-requests")
async def create_request(
    request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(RequestIn, await request.body())
    service = _module(body.module)
    ensure_section(conn, actor, service)
    description = _description(body.description, "The reason")
    if not description:
        raise _invalid("Please write what the payment is for.")
    amount = check_amount(body.amount_poisha)
    case = _case(conn, service, _uuid(body.case_id, ApiError("NOT_FOUND", 404, "Case not found.")), lock=True)
    _ensure_open(case)
    row = conn.execute(
        text(
            "INSERT INTO payment_requests (ref, module, applicant_id, application_id, enrolment_id, kind, "
            "description, amount_poisha, created_by_kind, created_by_admin) VALUES (:ref, :m, :a, :app, :enr, "
            "'requested', :d, :amount, 'staff', :by) RETURNING *"
        ),
        {
            "ref": _new_ref(conn), "m": service, "a": case["applicant_id"], "app": case["application_id"],
            "enr": case["enrolment_id"], "d": description, "amount": amount, "by": actor.id,
        },
    ).mappings().one()
    if case["application_id"] is not None:
        add_event(conn, case["application_id"], actor, f"Payment requested: {description} ({money_text(amount)}, {row['ref']})")
    notify_person(
        conn,
        case["applicant_id"],
        service,
        "payment_requested",
        f"Payment requested - {row['ref']}",
        f"Please pay {money_text(amount)} for {description} ({case['title']}, {case['ref']}). "
        f"You can pay it under Payments due in your profile.",
        case["application_id"],
    )
    write_audit(conn, actor, "payment_request.created", f"{row['ref']} · {case['ref']} · {money_text(amount)}")
    return _one(conn, row["id"])


@router.post("/admin/payment-requests/{request_id}/cancel")
def cancel_request(
    request_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    uid = _uuid(request_id, _not_found())
    module = conn.execute(text("SELECT module FROM payment_requests WHERE id = :id"), {"id": uid}).scalar_one_or_none()
    if module is None:
        raise _not_found()
    ensure_section(conn, actor, module)
    row = conn.execute(text("SELECT * FROM payment_requests WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one()
    if row["status"] != "open":
        raise ApiError("CONFLICT", 409, "Only an open payment request can be cancelled.")
    live = _settle_started(conn, uid)
    row = conn.execute(text("SELECT * FROM payment_requests WHERE id = :id"), {"id": uid}).mappings().one()
    if row["status"] == "paid" or live is not None:
        raise ApiError("CONFLICT", 409, "A payment for this request has started or is waiting for verification, so it cannot be cancelled now.")
    if row["status"] == "open":
        conn.execute(
            text("UPDATE payment_requests SET status = 'cancelled', cancelled_at = now() WHERE id = :id"), {"id": uid}
        )
    if row["application_id"] is not None:
        add_event(conn, row["application_id"], actor, f"Payment request cancelled ({row['ref']})")
    write_audit(conn, actor, "payment_request.cancelled", row["ref"])
    return _one(conn, uid)


# ---------------------------------------------------------------- applicant


class OwnPaymentIn(PayIn):
    case_id: str = Field(max_length=60)
    amount_poisha: StrictInt
    note: str = Field(default="", max_length=1000)


def _path_module(module: str) -> Module:
    if module not in MODULES:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return cast(Module, module)


@router.get("/me/{module}/payment-requests")
def my_requests(
    module: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    service = _path_module(module)
    rows = conn.execute(
        text(_SELECT + "WHERE r.module = :m AND r.applicant_id = :a ORDER BY r.created_at DESC, r.id LIMIT 200"),
        {"m": service, "a": me.account["id"]},
    ).mappings()
    return {"items": [request_view(r) for r in rows]}


@router.post("/me/{module}/payment-requests/{request_id}/pay")
async def pay_request(
    module: str,
    request_id: str,
    request: Request,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    service = _path_module(module)
    body = parse_body(PayIn, await request.body())
    row = conn.execute(
        text("SELECT * FROM payment_requests WHERE id = :id AND module = :m AND applicant_id = :a FOR UPDATE"),
        {"id": _uuid(request_id, _not_found()), "m": service, "a": me.account["id"]},
    ).mappings().one_or_none()
    if row is None:
        raise _not_found()
    if row["status"] == "paid":
        raise ApiError("CONFLICT", 409, "This payment is already paid.")
    if row["status"] != "open":
        raise ApiError("CONFLICT", 409, "This payment request was cancelled.")
    case = _case(conn, service, row["application_id"] or row["enrolment_id"], me.account["id"])
    return start_payment(
        conn, me, service, "request", row["id"], _purpose(row, case), int(row["amount_poisha"]), body,
        ip=client_ip(request) or "",
    )


@router.post("/me/{module}/own-payments")
async def pay_own_amount(
    module: str, request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    service = _path_module(module)
    body = parse_body(OwnPaymentIn, await request.body())
    note = _description(body.note, "The note") or "Payment"
    amount = check_amount(body.amount_poisha)
    case = _case(conn, service, _uuid(body.case_id, ApiError("NOT_FOUND", 404, "Case not found.")), me.account["id"], lock=True)
    _ensure_open(case)
    row = conn.execute(
        text(
            "INSERT INTO payment_requests (ref, module, applicant_id, application_id, enrolment_id, kind, "
            "description, amount_poisha, created_by_kind) VALUES (:ref, :m, :a, :app, :enr, 'own', :d, :amount, "
            "'applicant') RETURNING *"
        ),
        {
            "ref": _new_ref(conn), "m": service, "a": me.account["id"], "app": case["application_id"],
            "enr": case["enrolment_id"], "d": note, "amount": amount,
        },
    ).mappings().one()
    # start_payment writes the audit row (payment.started) for this one change.
    return start_payment(
        conn, me, service, "request", row["id"], _purpose(row, case), amount, PayIn(
            method=body.method, phone=body.phone, manual_ref=body.manual_ref
        ),
        ip=client_ip(request) or "",
    )
