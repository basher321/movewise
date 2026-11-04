"""Finance (spec B07 / F09): payments to verify, refunds, outstanding fees, the ledger and
invoices. Super admin and finance only; section admins may read their module's invoices.
Every change writes exactly one audit row.
"""

import csv
import io
from datetime import date
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.deps import get_current_actor, require_finance_or_super
from app.catalog import default_fees
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULES, read_licence, today_dhaka
from app.payments.invoices import METHOD_LABELS, invoice_view
from app.payments.ledger import CATEGORIES, CATEGORY_LABELS, add_entry
from app.payments.service import ON_REFUNDED, lock_payment, mark_paid, money_text, notify_person, payment_event
from app.routers.pay import _email_status, refund_view

router = APIRouter()

PAGE_SIZE = 100
MAX_TEXT = 500


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _done() -> ApiError:
    return ApiError("CONFLICT", 409, "Already done.")


def _uuid(value: str, what: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, f"{what} not found.") from None


def _text(value: str, label: str, required: bool = True, max_len: int = MAX_TEXT) -> str:
    cleaned = value.strip()
    if required and not cleaned:
        raise _invalid(f"Please fill in: {label}.")
    if len(cleaned) > max_len:
        raise _invalid(f"{label} must be at most {max_len} characters.")
    return cleaned


# ---------------------------------------------------------------- payments to verify

_PENDING = text(
    "SELECT p.*, a.name AS p_name, a.email AS p_email FROM payments p "
    "JOIN applicant_accounts a ON a.id = p.applicant_id WHERE p.status = 'pending_verify' ORDER BY p.created_at, p.id"
)


@router.get("/admin/payments/pending")
def pending_payments(
    actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(r["id"]),
            "name": r["p_name"],
            "email": r["p_email"],
            "purpose": r["purpose"],
            "module": r["module"],
            "method": r["method"],
            "method_label": METHOD_LABELS[r["method"]],
            "manual_ref": r["manual_ref"],
            "gateway_ref": r["gateway_ref"],
            "payer_phone": r["payer_phone"],
            "note": r["decision_note"],
            "amount_poisha": int(r["amount_poisha"]),
            "created_at": r["created_at"].isoformat(),
        }
        for r in conn.execute(_PENDING).mappings()
    ]


class ReasonIn(BaseModel):
    reason: str = Field(max_length=5000)


@router.post("/admin/payments/{payment_id}/verify")
def verify_payment(
    payment_id: str, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    payment = lock_payment_or_404(conn, payment_id)
    if payment["status"] != "pending_verify":
        raise _done()
    paid = mark_paid(conn, payment["id"], actor, verified_by=actor.id)
    return {"id": str(paid["id"]), "status": paid["status"]}


def lock_payment_or_404(conn: Connection, payment_id: str) -> RowMapping:
    uid = _uuid(payment_id, "Payment")
    if conn.execute(text("SELECT 1 FROM payments WHERE id = :id"), {"id": uid}).first() is None:
        raise ApiError("NOT_FOUND", 404, "Payment not found.")
    return lock_payment(conn, uid)


@router.post("/admin/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: str, request: Request, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    payment = lock_payment_or_404(conn, payment_id)
    reason = _text(parse_body(ReasonIn, await request.body()).reason, "Reason")
    if payment["status"] != "pending_verify":
        raise _done()
    conn.execute(
        text("UPDATE payments SET status = 'rejected', decision_note = :n, verified_by = :by WHERE id = :id"),
        {"n": reason, "by": actor.id, "id": payment["id"]},
    )
    payment_event(conn, payment["id"], "rejected", {"reason": reason, "by": actor.name})
    notify_person(
        conn,
        payment["applicant_id"],
        payment["module"],
        "payment_rejected",
        "We could not confirm your payment",
        f"Your payment of {money_text(payment['amount_poisha'])} for {payment['purpose']} could not be confirmed.\n\n"
        f"Reason: {reason}\n\nYou can pay again from your profile.",
        payment["ref_id"] if payment["ref_type"] == "application" else None,
    )
    write_audit(conn, actor, "payment.rejected", f"{payment['tran_id']} · {reason}")
    return {"id": str(payment["id"]), "status": "rejected"}


# ---------------------------------------------------------------- refunds

_REFUNDS = text(
    "SELECT r.*, a.name AS p_name, a.email AS p_email, p.purpose FROM refunds r "
    "JOIN applicant_accounts a ON a.id = r.applicant_id JOIN payments p ON p.id = r.payment_id "
    "ORDER BY (r.status = 'requested') DESC, r.requested_at DESC, r.id"
)


@router.get("/admin/refunds")
def list_refunds(
    actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return [
        {**refund_view(r), "name": r["p_name"], "email": r["p_email"], "description": r["purpose"]}
        for r in conn.execute(_REFUNDS).mappings()
    ]


class ApproveIn(BaseModel):
    refund_method: str = Field(max_length=200)
    refund_ref: str = Field(max_length=200)


def _lock_refund(conn: Connection, refund_id: str) -> RowMapping:
    row = conn.execute(
        text("SELECT * FROM refunds WHERE id = :id FOR UPDATE"), {"id": _uuid(refund_id, "Refund")}
    ).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Refund not found.")
    return row


@router.post("/admin/refunds/{refund_id}/approve")
async def approve_refund(
    refund_id: str, request: Request, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    refund = _lock_refund(conn, refund_id)
    body = parse_body(ApproveIn, await request.body())
    method = _text(body.refund_method, "Refunded via", max_len=100)
    ref = _text(body.refund_ref, "Refund reference", max_len=100)
    if refund["status"] != "requested":
        raise _done()
    payment = lock_payment(conn, refund["payment_id"])
    row = conn.execute(
        text(
            "UPDATE refunds SET status = 'approved', decided_by = :by, decided_at = now(), refund_method = :m, "
            "refund_ref = :r WHERE id = :id RETURNING *"
        ),
        {"by": actor.id, "m": method, "r": ref, "id": refund["id"]},
    ).mappings().one()
    if refund["invoice_no"]:
        conn.execute(
            text("UPDATE invoices SET refunded = true, refunded_at = now() WHERE no = :no"), {"no": refund["invoice_no"]}
        )
    conn.execute(text("UPDATE payments SET status = 'refunded' WHERE id = :id"), {"id": payment["id"]})
    on_refunded = ON_REFUNDED.get(payment["ref_type"])
    if on_refunded is not None:
        on_refunded(conn, payment)
    person = conn.execute(
        text("SELECT name, email FROM applicant_accounts WHERE id = :id"), {"id": refund["applicant_id"]}
    ).one()
    add_entry(
        conn,
        direction="out",
        category="refund",
        party=person.name,
        email=person.email or "",
        description=f"Refund · {refund['invoice_no'] or payment['tran_id']} · {ref}",
        method=method,
        amount_poisha=int(refund["amount_poisha"]),
        auto=True,
        payment_id=payment["id"],
        created_by=actor.id,
    )
    payment_event(conn, payment["id"], "refunded", {"refund_method": method, "refund_ref": ref})
    notify_person(
        conn,
        refund["applicant_id"],
        payment["module"],
        "refund_approved",
        "Your refund is on its way",
        f"We refunded {money_text(refund['amount_poisha'])} for {payment['purpose']} via {method} "
        f"(reference {ref}).",
        payment["ref_id"] if payment["ref_type"] == "application" else None,
    )
    write_audit(conn, actor, "refund.approved", f"{refund['invoice_no'] or payment['tran_id']} · {money_text(refund['amount_poisha'])}")
    return refund_view(row)


@router.post("/admin/refunds/{refund_id}/decline")
async def decline_refund(
    refund_id: str, request: Request, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    refund = _lock_refund(conn, refund_id)
    reason = _text(parse_body(ReasonIn, await request.body()).reason, "Reason")
    if refund["status"] != "requested":
        raise _done()
    row = conn.execute(
        text(
            "UPDATE refunds SET status = 'declined', decided_by = :by, decided_at = now(), decision_note = :n "
            "WHERE id = :id RETURNING *"
        ),
        {"by": actor.id, "n": reason, "id": refund["id"]},
    ).mappings().one()
    payment = conn.execute(text("SELECT * FROM payments WHERE id = :id"), {"id": refund["payment_id"]}).mappings().one()
    notify_person(
        conn,
        refund["applicant_id"],
        payment["module"],
        "refund_declined",
        "About your refund request",
        f"Your refund request for {payment['purpose']} was declined.\n\nReason: {reason}",
        payment["ref_id"] if payment["ref_type"] == "application" else None,
    )
    write_audit(conn, actor, "refund.declined", f"{refund['invoice_no'] or payment['tran_id']}")
    return refund_view(row)


# ---------------------------------------------------------------- outstanding

_OUTSTANDING_APPS = text(
    "SELECT a.id, a.ref, a.module, a.status, a.applicant_id, p.name, p.email, p.phone, "
    "COALESCE(u.name, v.title, vp.title) AS item_title, "
    "COALESCE(u.fee_override_poisha, v.fee_override_poisha, vp.fee_override_poisha) AS override, "
    "(SELECT row_to_json(x) FROM (SELECT pay.status, pay.amount_poisha FROM payments pay "
    "  WHERE pay.ref_type = 'application' AND pay.ref_id = a.id AND pay.status IN ('initiated', 'pending_verify') "
    "  ORDER BY pay.created_at DESC LIMIT 1) x) AS live "
    "FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id "
    "LEFT JOIN universities u ON u.id = a.university_id LEFT JOIN vacancies v ON v.id = a.vacancy_id "
    "LEFT JOIN visa_programs vp ON vp.id = a.visa_program_id "
    "WHERE a.status IN ('active', 'on_hold') AND NOT a.fee_paid AND a.module = ANY(:modules) "
    "ORDER BY a.created_at, a.id"
)

# B09 adds unpaid course enrolments here.
EXTRA_OUTSTANDING: list[Any] = []


def outstanding_items(conn: Connection, applicant_id: Any = None) -> list[dict[str, Any]]:
    licence = read_licence(conn)
    modules = [m for m in ("study", "job", "visa") if licence.licensed(m)]
    default: dict[str, int] = dict(default_fees(conn))
    items = []
    for r in conn.execute(_OUTSTANDING_APPS, {"modules": modules}).mappings():
        if applicant_id is not None and r["applicant_id"] != applicant_id:
            continue
        live = r["live"]
        amount = int(live["amount_poisha"]) if live else int(r["override"] or default[r["module"]])
        items.append(
            {
                "applicant_id": str(r["applicant_id"]),
                "name": r["name"],
                "email": r["email"],
                "phone": r["phone"],
                "module": r["module"],
                "ref_type": "application",
                "ref_id": str(r["id"]),
                "ref": r["ref"],
                "purpose": f"Application fee - {r['item_title']} ({r['ref']})",
                "status": "pending_verify" if live and live["status"] == "pending_verify" else "unpaid",
                "amount_poisha": amount,
            }
        )
    for extra in EXTRA_OUTSTANDING:
        items.extend(extra(conn, applicant_id))
    return items


@router.get("/admin/outstanding")
def list_outstanding(
    actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    items = outstanding_items(conn)
    return {"items": items, "total_poisha": sum(i["amount_poisha"] for i in items)}


@router.post("/admin/outstanding/{applicant_id}/remind")
def remind(
    applicant_id: str, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    uid = _uuid(applicant_id, "Applicant")
    items = [i for i in outstanding_items(conn, uid) if i["status"] == "unpaid"]
    if not items:
        raise ApiError("CONFLICT", 409, "This person has nothing unpaid.")
    lines = "\n".join(f"- {i['purpose']}: {money_text(i['amount_poisha'])}" for i in items)
    notify_person(
        conn,
        uid,
        items[0]["module"],
        "payment_reminder",
        "Payment reminder",
        f"This is a friendly reminder that these fees are still unpaid:\n{lines}\n\nYou can pay from your profile.",
    )
    write_audit(conn, actor, "payment.reminder", f"{items[0]['email']} · {len(items)} item(s)")
    return {"sent": True, "items": len(items)}


# ---------------------------------------------------------------- ledger

Period = Literal["all", "month"]

_ALL_ENTRIES = text(
    "SELECT e.*, (SELECT r.ref FROM ledger_entries r WHERE r.reverses_id = e.id) AS reversed_by, "
    "o.ref AS reverses_ref FROM ledger_entries e LEFT JOIN ledger_entries o ON o.id = e.reverses_id "
    "ORDER BY e.entry_date, e.at, e.id"
)


def _entry_view(row: RowMapping, balance: int) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "ref": row["ref"],
        "date": row["entry_date"].isoformat(),
        "at": row["at"].isoformat(),
        "direction": row["direction"],
        "category": row["category"],
        "category_label": CATEGORY_LABELS[row["category"]],
        "party": row["party"],
        "email": row["email"],
        "description": row["description"],
        "method": row["method"],
        "amount_poisha": int(row["amount_poisha"]),
        "auto": row["auto"],
        "reversed": row["reversed_by"] is not None,
        "reversed_by": row["reversed_by"],
        "reverses_ref": row["reverses_ref"],
        "balance_poisha": balance,
    }


def _month_start() -> date:
    return today_dhaka().replace(day=1)


def _entries(conn: Connection, direction: str, period: str) -> list[dict[str, Any]]:
    if direction not in ("", "all", "in", "out"):
        raise _invalid("Unknown direction.")
    if period not in ("all", "month"):
        raise _invalid("Unknown period.")
    balance = 0
    out = []
    start = _month_start()
    for row in conn.execute(_ALL_ENTRIES).mappings():
        amount = int(row["amount_poisha"])
        balance += amount if row["direction"] == "in" else -amount
        if direction in ("in", "out") and row["direction"] != direction:
            continue
        if period == "month" and row["entry_date"] < start:
            continue
        out.append(_entry_view(row, balance))
    out.reverse()  # newest first; the balance was counted oldest first
    return out


@router.get("/admin/ledger")
def list_ledger(
    direction: str = "all",
    period: str = "all",
    page: int = 1,
    actor: Actor = Depends(require_finance_or_super),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    entries = _entries(conn, direction, period)
    start = (page - 1) * PAGE_SIZE
    return {"items": entries[start : start + PAGE_SIZE], "total": len(entries), "page": page, "page_size": PAGE_SIZE}


class LedgerIn(BaseModel):
    direction: Literal["in", "out"]
    category: str = Field(max_length=40)
    date: date
    amount_poisha: StrictInt
    party: str = Field(max_length=2000)
    email: str = Field(default="", max_length=500)
    method: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=5000)


@router.post("/admin/ledger")
async def add_ledger_entry(
    request: Request, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(LedgerIn, await request.body())
    if body.category not in CATEGORIES[body.direction]:
        raise _invalid("Please choose a category.")
    if body.amount_poisha <= 0 or body.amount_poisha % 100 != 0:
        raise _invalid("Amount must be a whole number of taka above 0.")
    if body.date > today_dhaka():
        raise _invalid("The date cannot be in the future.")
    party = _text(body.party, "Received from / paid to", max_len=200)
    row = add_entry(
        conn,
        direction=body.direction,
        category=body.category,
        party=party,
        email=_text(body.email, "Email", required=False, max_len=254),
        description=_text(body.note, "Note", required=False),
        method=_text(body.method, "Method", required=False, max_len=100),
        amount_poisha=body.amount_poisha,
        auto=False,
        entry_date=body.date,
        created_by=actor.id,
    )
    sign = "+" if body.direction == "in" else "-"
    write_audit(conn, actor, "ledger.added", f"{row['ref']} · {CATEGORY_LABELS[body.category]} · {sign}{money_text(body.amount_poisha)}")
    return {"id": str(row["id"]), "ref": row["ref"]}


@router.post("/admin/ledger/{entry_id}/reverse")
async def reverse_entry(
    entry_id: str, request: Request, actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    uid = _uuid(entry_id, "Entry")
    conn.execute(text("SELECT pg_advisory_xact_lock(3000007)"))
    entry = conn.execute(text("SELECT * FROM ledger_entries WHERE id = :id"), {"id": uid}).mappings().one_or_none()
    if entry is None:
        raise ApiError("NOT_FOUND", 404, "Entry not found.")
    reason = _text(parse_body(ReasonIn, await request.body()).reason, "Reason")
    if entry["auto"]:
        raise ApiError("CONFLICT", 409, "Automatic entries cannot be reversed. Use a refund to return a fee.")
    if entry["reverses_id"] is not None:
        raise ApiError("CONFLICT", 409, "A reversal cannot be reversed. Add a new entry instead.")
    if conn.execute(text("SELECT 1 FROM ledger_entries WHERE reverses_id = :id"), {"id": uid}).first():
        raise _done()
    opposite: Literal["in", "out"] = "out" if entry["direction"] == "in" else "in"
    row = add_entry(
        conn,
        direction=opposite,
        category="otherout" if opposite == "out" else "otherin",
        party=entry["party"],
        email=entry["email"],
        description=f"Reversal of {entry['ref']}: {reason}",
        method=entry["method"],
        amount_poisha=int(entry["amount_poisha"]),
        auto=False,
        reverses_id=uid,
        created_by=actor.id,
    )
    write_audit(conn, actor, "ledger.reversed", f"{entry['ref']} -> {row['ref']} · {reason}")
    return {"id": str(row["id"]), "ref": row["ref"]}


@router.get("/admin/ledger/summary")
def ledger_summary(
    period: str = "all", actor: Actor = Depends(require_finance_or_super), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    entries = _entries(conn, "all", "all")
    balance = entries[0]["balance_poisha"] if entries else 0
    chosen = _entries(conn, "all", period)
    by_source: dict[str, int] = {}
    by_method: dict[str, int] = {}
    by_expense: dict[str, int] = {}
    money_in = money_out = 0
    for e in chosen:
        if e["direction"] == "in":
            money_in += e["amount_poisha"]
            by_source[e["category"]] = by_source.get(e["category"], 0) + e["amount_poisha"]
            method = e["method"] or "Other"
            by_method[method] = by_method.get(method, 0) + e["amount_poisha"]
        else:
            money_out += e["amount_poisha"]
            by_expense[e["category"]] = by_expense.get(e["category"], 0) + e["amount_poisha"]
    return {
        "balance_all_time_poisha": balance,
        "in_poisha": money_in,
        "out_poisha": money_out,
        "net_poisha": money_in - money_out,
        "by_source": by_source,
        "by_method": by_method,
        "by_expense": by_expense,
        "category_labels": CATEGORY_LABELS,
    }


def _csv_money(poisha: int) -> str:
    sign = "-" if poisha < 0 else ""
    value = abs(poisha)
    return f"{sign}{value // 100}.{value % 100:02d}"


def _csv_safe(value: str) -> str:
    # Stops spreadsheet formulas in names or notes from running when the file is opened.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get("/admin/ledger.csv")
def ledger_csv(
    direction: str = "all",
    period: str = "all",
    actor: Actor = Depends(require_finance_or_super),
    conn: Connection = Depends(get_conn),
) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["Date", "Type", "Category", "Party", "Email", "Description", "Method", "Reference", "Amount"])
    for e in reversed(_entries(conn, direction, period)):
        amount = e["amount_poisha"] if e["direction"] == "in" else -e["amount_poisha"]
        writer.writerow(
            [
                e["date"],
                "Money in" if e["direction"] == "in" else "Money out",
                e["category_label"],
                _csv_safe(e["party"]),
                _csv_safe(e["email"]),
                _csv_safe(e["description"]),
                _csv_safe(e["method"]),
                e["ref"],
                _csv_money(amount),
            ]
        )
    name = f"ledger-{today_dhaka().isoformat()}.csv"
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )


# ---------------------------------------------------------------- invoices


def _invoice_modules(conn: Connection, actor: Actor, module: str) -> list[str]:
    """Finance and super admin see all; a section admin sees the modules of their sections."""
    if module and module not in MODULES:
        raise _invalid("Unknown module.")
    if actor.role in ("super_admin", "finance"):
        return [module] if module else list(MODULES)
    if actor.role == "admin":
        licence = read_licence(conn)
        mine = [m for m in actor.sections if licence.licensed(m)]
        if module:
            if module not in mine:
                raise ApiError("FORBIDDEN", 403, "You do not have access to these invoices.")
            return [module]
        if mine:
            return mine
    raise ApiError("FORBIDDEN", 403, "You do not have access to invoices.")


@router.get("/admin/invoices")
def list_invoices(
    q: str = "",
    module: str = "",
    page: int = 1,
    actor: Actor = Depends(get_current_actor),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    modules = _invoice_modules(conn, actor, module)
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    params: dict[str, Any] = {"modules": modules}
    where = "module = ANY(:modules)"
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where += " AND (no ILIKE :q OR name ILIKE :q OR email ILIKE :q)"
    total = int(conn.execute(text(f"SELECT count(*) FROM invoices WHERE {where}"), params).scalar_one())
    rows = conn.execute(
        text(f"SELECT * FROM invoices WHERE {where} ORDER BY issued_at DESC, no DESC LIMIT :l OFFSET :o"),
        {**params, "l": 50, "o": (page - 1) * 50},
    ).mappings()
    items = [invoice_view(r, _email_status(conn, r["no"])) for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": 50}


@router.get("/admin/invoices/{no}")
def get_invoice(no: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(text("SELECT * FROM invoices WHERE no = :no"), {"no": no}).mappings().one_or_none()
    if row is None:
        # Same answer for staff without invoice access, so numbers cannot be probed.
        _invoice_modules(conn, actor, "")
        raise ApiError("NOT_FOUND", 404, "Invoice not found.")
    _invoice_modules(conn, actor, cast(str, row["module"]))
    return invoice_view(row, _email_status(conn, row["no"]))
