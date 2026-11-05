"""Paying the application fee, the payment result, invoices, refund requests and the gateway
callbacks (spec B07).

Applicants reach only their own records (others are 404). Gateway callbacks are public and
exempt from the Origin check, but never trusted on their own: every success is checked with
the gateway by the server before anything is marked paid.
"""

import logging
import re
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.applications import add_event, fee_now, item_row, item_title, parse_id
from app.audit import write_audit
from app.auth.deps import Applicant, current_applicant, current_applicant_row
from app.auth.inputs import normalize_phone
from app.config import get_settings
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULES, Module
from app.payments import bkash, sslcommerz
from app.payments.gateway import GatewayError, gateway_config
from app.payments.invoices import invoice_view
from app.payments.service import (
    LIVE_STATUSES,
    bkash_status,
    confirm_bkash,
    confirm_sslcommerz,
    money_text,
    new_tran_id,
    payment_event,
    record_end,
    refresh_initiated,
    register_on_paid,
)
from app.stages import APP_MODULES, AppModule

logger = logging.getLogger("app")

router = APIRouter()

BD_MOBILE = re.compile(r"(?:\+?88)?01[3-9]\d{8}")
METHODS = ("sslcommerz", "bkash", "manual")
MAX_REASON = 500


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _app_module(module: str) -> AppModule:
    if module not in APP_MODULES:
        raise ApiError("NOT_FOUND", 404, "Not found.")
    return cast(AppModule, module)


# ---------------------------------------------------------------- application on_paid


def _application_paid(conn: Connection, payment: RowMapping) -> None:
    conn.execute(text("UPDATE applications SET fee_paid = true WHERE id = :id"), {"id": payment["ref_id"]})
    add_event(conn, payment["ref_id"], None, f"Application fee paid ({money_text(payment['amount_poisha'])})")


register_on_paid("application", _application_paid)


# ---------------------------------------------------------------- start a payment


class PayIn(BaseModel):
    method: str = Field(max_length=20)
    phone: str = Field(default="", max_length=40)
    manual_ref: str = Field(default="", max_length=200)


def _check_method_on(conn: Connection, method: str) -> None:
    row = conn.execute(
        text("SELECT sslcommerz_enabled, bkash_enabled, manual_enabled FROM settings WHERE singleton = 'settings'")
    ).one()
    if not row._mapping[f"{method}_enabled"]:
        raise _invalid("This payment method is not available.")


def _payment_view(conn: Connection, payment: RowMapping) -> dict[str, Any]:
    invoice_no = conn.execute(
        text("SELECT no FROM invoices WHERE payment_id = :id"), {"id": payment["id"]}
    ).scalar_one_or_none()
    return {
        "id": str(payment["id"]),
        "status": payment["status"],
        "method": payment["method"],
        "module": payment["module"],
        "ref_type": payment["ref_type"],
        "ref_id": str(payment["ref_id"]),
        "amount_poisha": int(payment["amount_poisha"]),
        "purpose": payment["purpose"],
        "invoice_no": invoice_no,
        "note": payment["decision_note"],
        "created_at": payment["created_at"].isoformat(),
        "paid_at": payment["paid_at"].isoformat() if payment["paid_at"] else None,
    }


def _payer_email(conn: Connection, own: str | None) -> str:
    """SSLCommerz needs an email. Email is optional for applicants: the company email stands in
    (the receipt still reaches the person in their profile and by WhatsApp)."""
    if own:
        return own
    company = conn.execute(
        text("SELECT email, mail_sender_email FROM settings WHERE singleton = 'settings'")
    ).one()
    fallback = company.email or company.mail_sender_email
    if not fallback:
        raise _invalid("Please add your email in your profile to pay by card, or choose another method.")
    return str(fallback)


def start_payment(
    conn: Connection,
    me: Applicant,
    module: Module,
    ref_type: str,
    ref_id: Any,
    purpose: str,
    amount_poisha: int,
    body: PayIn,
) -> dict[str, Any]:
    """Shared by application fees and (B09) course enrolments. The caller has locked the
    application or enrolment row, so two starts for the same item run one after the other."""
    method = body.method
    if method not in METHODS:
        raise _invalid("Please choose a payment method.")
    phone = normalize_phone(body.phone)
    if not BD_MOBILE.fullmatch(phone):
        raise _invalid("Please enter a valid Bangladeshi mobile number, like 01712345678.")
    manual_ref = body.manual_ref.strip()
    if method == "manual" and not manual_ref:
        raise _invalid("Please enter the bank or receipt reference.")
    _check_method_on(conn, method)
    config = None
    if method != "manual":
        config = gateway_config(conn, method)  # type: ignore[arg-type]
        if config is None:
            raise _invalid("This payment method is not set up yet. Please choose another one.")

    live = conn.execute(
        text("SELECT * FROM payments WHERE ref_type = :t AND ref_id = :r AND status = ANY(:s) FOR UPDATE"),
        {"t": ref_type, "r": ref_id, "s": list(LIVE_STATUSES)},
    ).mappings().one_or_none()
    if live is not None and live["status"] == "initiated":
        live = refresh_initiated(conn, live)
    if live is not None and live["status"] == "paid":
        raise ApiError("CONFLICT", 409, "This fee is already paid.")
    if live is not None and live["status"] == "pending_verify":
        raise ApiError("CONFLICT", 409, "A payment for this fee is waiting for verification.")

    tran_id = new_tran_id(conn)
    payment = conn.execute(
        text(
            "INSERT INTO payments (applicant_id, module, ref_type, ref_id, purpose, amount_poisha, method, status, "
            "tran_id, manual_ref, payer_phone) VALUES (:a, :m, :t, :r, :p, :amount, :method, :status, :tran, "
            ":manual_ref, :phone) RETURNING *"
        ),
        {
            "a": me.account["id"],
            "m": module,
            "t": ref_type,
            "r": ref_id,
            "p": purpose,
            "amount": amount_poisha,
            "method": method,
            "status": "pending_verify" if method == "manual" else "initiated",
            "tran": tran_id,
            "manual_ref": manual_ref or None,
            "phone": phone,
        },
    ).mappings().one()
    write_audit(conn, me.actor, "payment.started", f"{tran_id} · {method} · {money_text(amount_poisha)}")
    if method == "manual":
        payment_event(conn, payment["id"], "manual_submitted", {"manual_ref": manual_ref})
        return {"payment_id": str(payment["id"]), "status": "pending_verify"}

    assert config is not None
    api = get_settings().api_base
    try:
        if method == "sslcommerz":
            account = me.account
            redirect_url, session = sslcommerz.start(
                config,
                tran_id,
                amount_poisha,
                purpose,
                sslcommerz.Customer(
                    name=account["name"], email=_payer_email(conn, account["email"]), phone=phone,
                    city="", country=account["country"] or "",
                ),
                {
                    "success": f"{api}/api/pay/sslcommerz/success",
                    "fail": f"{api}/api/pay/sslcommerz/fail",
                    "cancel": f"{api}/api/pay/sslcommerz/cancel",
                    "ipn": f"{api}/api/pay/sslcommerz/ipn",
                },
            )
        else:
            session, redirect_url = bkash.create(config, tran_id, amount_poisha, phone, f"{api}/api/pay/bkash/callback")
    except GatewayError as exc:
        logger.warning("Payment start failed: %s", exc)
        raise ApiError(
            "INTERNAL", 500, "The payment gateway is not answering. Please try again in a few minutes."
        ) from None
    conn.execute(
        text("UPDATE payments SET gateway_session = :s WHERE id = :id"), {"s": session or None, "id": payment["id"]}
    )
    payment_event(conn, payment["id"], "started", {"method": method})
    return {"payment_id": str(payment["id"]), "redirect_url": redirect_url}


@router.post("/me/{module}/applications/{app_id}/pay")
async def pay_application(
    module: str, app_id: str, request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app_module = _app_module(module)
    app = conn.execute(
        text("SELECT * FROM applications WHERE id = :id AND applicant_id = :a AND module = :m FOR UPDATE"),
        {"id": parse_id(app_id), "a": me.account["id"], "m": app_module},
    ).mappings().one_or_none()
    if app is None:
        raise ApiError("NOT_FOUND", 404, "Application not found.")
    body = parse_body(PayIn, await request.body())
    if app["fee_paid"]:
        raise ApiError("CONFLICT", 409, "This fee is already paid.")
    if app["status"] not in ("active", "on_hold"):
        raise ApiError("CONFLICT", 409, "Only an active or on-hold application can be paid for.")
    item = item_row(conn, app)
    purpose = f"Application fee - {item_title(app_module, item)} ({app['ref']})"
    return start_payment(conn, me, app_module, "application", app["id"], purpose, fee_now(conn, app_module, item), body)


# ---------------------------------------------------------------- payment result


@router.get("/me/payments/{payment_id}")
def my_payment(payment_id: str, request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    try:
        uid = UUID(payment_id)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, "Payment not found.") from None
    payment = conn.execute(text("SELECT * FROM payments WHERE id = :id"), {"id": uid}).mappings().one_or_none()
    signed_in = [m for m in MODULES if current_applicant_row(request, conn, m) is not None]
    if not signed_in:
        raise ApiError("UNAUTHENTICATED", 401, "Please sign in.")
    if payment is None:
        raise ApiError("NOT_FOUND", 404, "Payment not found.")
    me = current_applicant_row(request, conn, payment["module"])
    if me is None or me["id"] != payment["applicant_id"]:
        raise ApiError("NOT_FOUND", 404, "Payment not found.")
    if payment["status"] == "initiated" and payment["method"] == "bkash":
        # The next status check can finish a payment whose callback was lost.
        payment = bkash_status(conn, conn.execute(
            text("SELECT * FROM payments WHERE id = :id FOR UPDATE"), {"id": uid}
        ).mappings().one())
    return _payment_view(conn, payment)


# ---------------------------------------------------------------- invoices and refunds


def _email_status(conn: Connection, invoice_no: str) -> str:
    status = conn.execute(
        text(
            "SELECT status FROM notifications WHERE event = 'payment_received' AND channel = 'email' "
            "AND subject = :s ORDER BY at DESC LIMIT 1"
        ),
        {"s": f"Payment received - {invoice_no}"},
    ).scalar_one_or_none()
    return str(status) if status else "none"


@router.get("/me/{module}/invoices")
def my_invoices(
    module: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT i.*, r.status AS refund_status FROM invoices i LEFT JOIN refunds r ON r.invoice_no = i.no "
            "WHERE i.applicant_id = :a AND i.module = :m ORDER BY i.issued_at DESC, i.no DESC"
        ),
        {"a": me.account["id"], "m": module},
    ).mappings()
    return [{**invoice_view(r), "refund_status": r["refund_status"]} for r in rows]


@router.get("/me/{module}/invoices/{no}")
def my_invoice(
    module: str, no: str, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = conn.execute(
        text(
            "SELECT i.*, r.status AS refund_status FROM invoices i LEFT JOIN refunds r ON r.invoice_no = i.no "
            "WHERE i.no = :no AND i.applicant_id = :a AND i.module = :m"
        ),
        {"no": no, "a": me.account["id"], "m": module},
    ).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Invoice not found.")
    return {**invoice_view(row), "refund_status": row["refund_status"]}


class RefundIn(BaseModel):
    invoice_no: str = Field(max_length=100)
    reason: str = Field(max_length=5000)


def refund_view(row: RowMapping) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "invoice_no": row["invoice_no"],
        "amount_poisha": int(row["amount_poisha"]),
        "reason": row["reason"],
        "status": row["status"],
        "decision_note": row["decision_note"],
        "refund_method": row["refund_method"],
        "refund_ref": row["refund_ref"],
        "requested_at": row["requested_at"].isoformat(),
        "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None,
    }


@router.post("/me/{module}/refunds")
async def request_refund(
    module: str, request: Request, me: Applicant = Depends(current_applicant), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(RefundIn, await request.body())
    reason = body.reason.strip()
    if not reason:
        raise _invalid("Please give a reason.")
    if len(reason) > MAX_REASON:
        raise _invalid(f"The reason must be at most {MAX_REASON} characters.")
    invoice = conn.execute(
        text("SELECT * FROM invoices WHERE no = :no AND applicant_id = :a AND module = :m FOR UPDATE"),
        {"no": body.invoice_no.strip(), "a": me.account["id"], "m": module},
    ).mappings().one_or_none()
    if invoice is None:
        raise ApiError("NOT_FOUND", 404, "Invoice not found.")
    if invoice["refunded"]:
        raise ApiError("CONFLICT", 409, "This invoice is already refunded.")
    if conn.execute(text("SELECT 1 FROM refunds WHERE invoice_no = :no"), {"no": invoice["no"]}).first():
        raise ApiError("CONFLICT", 409, "A refund for this invoice was already requested.")
    row = conn.execute(
        text(
            "INSERT INTO refunds (invoice_no, payment_id, applicant_id, amount_poisha, reason) "
            "VALUES (:no, :p, :a, :amount, :reason) RETURNING *"
        ),
        {
            "no": invoice["no"],
            "p": invoice["payment_id"],
            "a": me.account["id"],
            "amount": invoice["amount_poisha"],
            "reason": reason,
        },
    ).mappings().one()
    write_audit(conn, me.actor, "refund.requested", invoice["no"])
    return refund_view(row)


# ---------------------------------------------------------------- gateway callbacks


def _result_redirect(payment_id: Any) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().site_base}/payment/result?id={payment_id}", status_code=303)


def _not_found_callback(what: str) -> ApiError:
    logger.warning("Payment callback for an unknown %s", what)
    return ApiError("NOT_FOUND", 404, "Payment not found.")


async def _ssl_form(request: Request) -> dict[str, str]:
    try:
        form = await request.form(max_files=0, max_fields=200)
    except Exception:
        return {}
    return {k: v for k, v in form.items() if isinstance(v, str)}


def _ssl_payment(conn: Connection, form: dict[str, str]) -> RowMapping:
    tran_id = form.get("tran_id", "")[:30]
    payment = conn.execute(
        text("SELECT * FROM payments WHERE tran_id = :t AND method = 'sslcommerz'"), {"t": tran_id}
    ).mappings().one_or_none()
    if payment is None:
        raise _not_found_callback("tran_id")
    return payment


@router.post("/pay/sslcommerz/success")
async def sslcommerz_success(request: Request, conn: Connection = Depends(get_conn)) -> RedirectResponse:
    form = await _ssl_form(request)
    payment = _ssl_payment(conn, form)
    confirm_sslcommerz(conn, payment, form.get("val_id", "")[:100])
    return _result_redirect(payment["id"])


@router.post("/pay/sslcommerz/ipn")
async def sslcommerz_ipn(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, str]:
    form = await _ssl_form(request)
    payment = _ssl_payment(conn, form)
    confirm_sslcommerz(conn, payment, form.get("val_id", "")[:100])
    return {"status": "received"}


@router.post("/pay/sslcommerz/fail")
async def sslcommerz_fail(request: Request, conn: Connection = Depends(get_conn)) -> RedirectResponse:
    payment = _ssl_payment(conn, await _ssl_form(request))
    record_end(conn, payment["id"], "failed", "gateway_fail", {"source": "fail callback"})
    return _result_redirect(payment["id"])


@router.post("/pay/sslcommerz/cancel")
async def sslcommerz_cancel(request: Request, conn: Connection = Depends(get_conn)) -> RedirectResponse:
    payment = _ssl_payment(conn, await _ssl_form(request))
    record_end(conn, payment["id"], "cancelled", "gateway_cancel", {"source": "cancel callback"})
    return _result_redirect(payment["id"])


@router.get("/pay/bkash/callback")
def bkash_callback(
    paymentID: str = "", status: str = "", conn: Connection = Depends(get_conn)
) -> RedirectResponse:
    payment = conn.execute(
        text("SELECT * FROM payments WHERE method = 'bkash' AND gateway_session = :s"), {"s": paymentID[:100]}
    ).mappings().one_or_none()
    if payment is None or not paymentID:
        raise _not_found_callback("paymentID")
    if status == "success":
        confirm_bkash(conn, payment)
    elif status == "cancel":
        record_end(conn, payment["id"], "cancelled", "gateway_cancel", {"source": "bkash callback"})
    else:
        record_end(conn, payment["id"], "failed", "gateway_fail", {"source": "bkash callback", "status": status[:20]})
    return _result_redirect(payment["id"])
