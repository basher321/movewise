"""The payment service (spec B07), shared by application fees now and course enrolments (B09).

Marking paid is one transaction and idempotent: payment paid -> invoice -> ledger "in" ->
the on_paid handler of its ref_type -> notification -> audit -> payment event.
Gateway answers are never trusted on their own: success is accepted only after the server
checks it with the gateway, with the same transaction id, amount and currency.
"""

import json
import logging
import secrets
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.notify.outbox import queue_message
from app.payments import bkash, sslcommerz
from app.payments.gateway import GatewayConfig, GatewayError, gateway_config, poisha_from_taka, scrub
from app.payments.invoices import METHOD_LABELS, issue_invoice
from app.payments.ledger import add_entry

logger = logging.getLogger("app")

SYSTEM = Actor(id=None, name="System", role=None)
RISKY_NOTE = "High-risk payment - check before accepting"
DUPLICATE_REASON = "Duplicate payment - refund required"
LIVE_STATUSES = ("initiated", "pending_verify", "paid")
_TRAN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

OnPaid = Callable[[Connection, RowMapping], None]
ON_PAID: dict[str, OnPaid] = {}


def register_on_paid(ref_type: str, handler: OnPaid) -> None:
    ON_PAID[ref_type] = handler


# B09: what happens to the paid item when its payment is refunded (applications: nothing).
ON_REFUNDED: dict[str, OnPaid] = {}


def register_on_refunded(ref_type: str, handler: OnPaid) -> None:
    ON_REFUNDED[ref_type] = handler


def money_text(poisha: int) -> str:
    taka_part, rest = divmod(int(poisha), 100)
    return f"৳{taka_part:,}" if rest == 0 else f"৳{taka_part:,}.{rest:02d}"


def new_tran_id(conn: Connection) -> str:
    exists = text("SELECT 1 FROM payments WHERE tran_id = :t")
    while True:
        tran = "MW-" + "".join(secrets.choice(_TRAN_ALPHABET) for _ in range(12))
        if conn.execute(exists, {"t": tran}).first() is None:
            return tran


def payment_event(conn: Connection, payment_id: Any, kind: str, detail: Any = None, secret_values: tuple[str, ...] = ()) -> None:
    conn.execute(
        text("INSERT INTO payment_events (payment_id, kind, detail) VALUES (:p, :k, CAST(:d AS jsonb))"),
        {"p": payment_id, "k": kind, "d": json.dumps(scrub(detail or {}, secret_values))},
    )


def notify_person(
    conn: Connection, applicant_id: Any, module: str, event: str, subject: str, body: str, application_id: Any = None
) -> None:
    person = conn.execute(
        text("SELECT name, email, phone FROM applicant_accounts WHERE id = :id"), {"id": applicant_id}
    ).one()
    queue_message(
        conn, person.name, person.email, person.phone or None, module, event, subject, body, application_id  # type: ignore[arg-type]
    )


def _application_id(payment: RowMapping) -> Any:
    return payment["ref_id"] if payment["ref_type"] == "application" else None


def lock_payment(conn: Connection, payment_id: Any) -> RowMapping:
    return conn.execute(text("SELECT * FROM payments WHERE id = :id FOR UPDATE"), {"id": payment_id}).mappings().one()


def _set(conn: Connection, payment_id: Any, **values: Any) -> RowMapping:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    return conn.execute(
        text(f"UPDATE payments SET {sets} WHERE id = :id RETURNING *"), {**values, "id": payment_id}
    ).mappings().one()


def _ledger_in(conn: Connection, payment: RowMapping, description: str) -> None:
    person = conn.execute(
        text("SELECT name, email FROM applicant_accounts WHERE id = :id"), {"id": payment["applicant_id"]}
    ).one()
    add_entry(
        conn,
        direction="in",
        category=payment["module"],
        party=person.name,
        email=person.email or "",
        description=description,
        method=METHOD_LABELS[payment["method"]],
        amount_poisha=int(payment["amount_poisha"]),
        auto=True,
        payment_id=payment["id"],
    )


def mark_paid(
    conn: Connection, payment_id: Any, actor: Actor, gateway_ref: str | None = None, verified_by: Any = None
) -> RowMapping:
    """Idempotent: a payment that is already paid is returned unchanged."""
    payment = lock_payment(conn, payment_id)
    if payment["status"] == "paid":
        return payment
    payment = _set(
        conn,
        payment["id"],
        status="paid",
        paid_at=conn.execute(text("SELECT now()")).scalar_one(),
        gateway_ref=gateway_ref or payment["gateway_ref"],
        verified_by=verified_by,
    )
    invoice = issue_invoice(conn, payment)
    _ledger_in(conn, payment, f"{payment['purpose']} · {invoice['no']}")
    handler = ON_PAID.get(payment["ref_type"])
    if handler is not None:
        handler(conn, payment)
    notify_person(
        conn,
        payment["applicant_id"],
        payment["module"],
        "payment_received",
        f"Payment received - {invoice['no']}",
        f"We received {money_text(payment['amount_poisha'])} for {payment['purpose']}. "
        f"Your invoice is {invoice['no']}; you can open it in your profile.",
        _application_id(payment),
    )
    write_audit(conn, actor, "payment.paid", f"{invoice['no']} · {money_text(payment['amount_poisha'])}")
    payment_event(conn, payment["id"], "paid", {"invoice_no": invoice["no"], "by": actor.name})
    return payment


def _other_paid(conn: Connection, payment: RowMapping) -> RowMapping | None:
    return conn.execute(
        text(
            "SELECT * FROM payments WHERE ref_type = :t AND ref_id = :r AND id <> :id AND status = 'paid' "
            "FOR UPDATE"
        ),
        {"t": payment["ref_type"], "r": payment["ref_id"], "id": payment["id"]},
    ).mappings().one_or_none()


def _other_live(conn: Connection, payment: RowMapping) -> RowMapping | None:
    return conn.execute(
        text(
            "SELECT * FROM payments WHERE ref_type = :t AND ref_id = :r AND id <> :id "
            "AND status IN ('initiated', 'pending_verify') FOR UPDATE"
        ),
        {"t": payment["ref_type"], "r": payment["ref_id"], "id": payment["id"]},
    ).mappings().one_or_none()


def create_refund_request(conn: Connection, payment: RowMapping, invoice_no: str | None, reason: str) -> RowMapping:
    return conn.execute(
        text(
            "INSERT INTO refunds (invoice_no, payment_id, applicant_id, amount_poisha, reason) "
            "VALUES (:no, :p, :a, :amount, :reason) RETURNING *"
        ),
        {
            "no": invoice_no,
            "p": payment["id"],
            "a": payment["applicant_id"],
            "amount": payment["amount_poisha"],
            "reason": reason,
        },
    ).mappings().one()


def record_success(
    conn: Connection, payment_id: Any, gateway_ref: str | None, detail: Any, risky: bool = False
) -> RowMapping:
    """A success the server has checked with the gateway. Safe to call any number of times."""
    payment = lock_payment(conn, payment_id)
    if payment["status"] in ("paid", "duplicate", "refunded", "pending_verify"):
        return payment
    if _other_paid(conn, payment) is not None:
        # Money was taken twice: keep it as a duplicate (no invoice) and ask finance to refund it.
        payment = _set(conn, payment["id"], status="duplicate", gateway_ref=gateway_ref)
        _ledger_in(conn, payment, f"{payment['purpose']} · duplicate payment")
        create_refund_request(conn, payment, None, DUPLICATE_REASON)
        payment_event(conn, payment["id"], "duplicate", detail)
        write_audit(conn, SYSTEM, "payment.duplicate", f"{payment['tran_id']} · {money_text(payment['amount_poisha'])}")
        return payment
    if payment["status"] != "initiated":
        live = _other_live(conn, payment)
        if live is not None and live["status"] == "initiated":
            _set(conn, live["id"], status="abandoned")
            payment_event(conn, live["id"], "abandoned", {"reason": "another payment succeeded"})
        elif live is not None:
            payment = _set(conn, payment["id"], status="duplicate", gateway_ref=gateway_ref)
            _ledger_in(conn, payment, f"{payment['purpose']} · duplicate payment")
            create_refund_request(conn, payment, None, DUPLICATE_REASON)
            payment_event(conn, payment["id"], "duplicate", detail)
            write_audit(conn, SYSTEM, "payment.duplicate", payment["tran_id"])
            return payment
    if risky:
        payment = _set(conn, payment["id"], status="pending_verify", decision_note=RISKY_NOTE, gateway_ref=gateway_ref)
        payment_event(conn, payment["id"], "risky", detail)
        write_audit(conn, SYSTEM, "payment.needs_check", payment["tran_id"])
        return payment
    payment_event(conn, payment["id"], "confirmed", detail)
    return mark_paid(conn, payment["id"], SYSTEM, gateway_ref=gateway_ref)


def record_end(
    conn: Connection, payment_id: Any, status: Literal["failed", "cancelled", "abandoned"], kind: str, detail: Any
) -> RowMapping:
    """failed / cancelled / abandoned, only while the payment is still initiated."""
    payment = lock_payment(conn, payment_id)
    if payment["status"] != "initiated":
        return payment
    payment = _set(conn, payment["id"], status=status)
    payment_event(conn, payment["id"], kind, detail)
    write_audit(conn, SYSTEM, f"payment.{status}", payment["tran_id"])
    return payment


def record_mismatch(conn: Connection, payment_id: Any, detail: Any) -> RowMapping:
    payment = lock_payment(conn, payment_id)
    if payment["status"] not in ("initiated", "abandoned", "cancelled"):
        return payment
    payment = _set(conn, payment["id"], status="failed")
    payment_event(conn, payment["id"], "mismatch", detail)
    write_audit(conn, SYSTEM, "payment.mismatch", payment["tran_id"])
    logger.warning("Payment answer did not match: payment %s", payment["id"])
    return payment


# ---------------------------------------------------------------- SSLCommerz


def confirm_sslcommerz(conn: Connection, payment: RowMapping, val_id: str) -> RowMapping:
    config = gateway_config(conn, "sslcommerz")
    if config is None or not val_id:
        return payment
    try:
        data = sslcommerz.validate(config, val_id)
    except GatewayError:
        # Stays initiated; the IPN or the next check finishes it.
        logger.warning("SSLCommerz validation unreachable: payment %s", payment["id"])
        return payment
    secret_values = tuple(config.secrets.values())
    if data.get("status") not in ("VALID", "VALIDATED"):
        # INVALID_TRANSACTION and others: not paid.
        return record_end(conn, payment["id"], "failed", "invalid", scrub(data, secret_values))
    sent_amount = data.get("currency_amount") if data.get("currency_type") else data.get("amount")
    ok = (
        str(data.get("tran_id", "")) == payment["tran_id"]
        and poisha_from_taka(sent_amount) == int(payment["amount_poisha"])
        and str(data.get("currency_type") or data.get("currency")) == "BDT"
    )
    if not ok:
        return record_mismatch(conn, payment["id"], scrub(data, secret_values))
    risky = str(data.get("risk_level", "0")) == "1"
    return record_success(conn, payment["id"], str(data.get("bank_tran_id") or val_id), scrub(data, secret_values), risky)


# ---------------------------------------------------------------- bKash

_BKASH_ENDED = {"Failed": "failed", "Cancelled": "cancelled", "Expired": "failed", "Declined": "failed"}


def _bkash_check(conn: Connection, payment: RowMapping, data: dict[str, Any], secret_values: tuple[str, ...]) -> RowMapping:
    state = str(data.get("transactionStatus", ""))
    if state == "Completed":
        ok = poisha_from_taka(data.get("amount")) == int(payment["amount_poisha"]) and str(
            data.get("merchantInvoiceNumber", "")
        ) == payment["tran_id"]
        if not ok:
            return record_mismatch(conn, payment["id"], scrub(data, secret_values))
        return record_success(conn, payment["id"], str(data.get("trxID", "")) or None, scrub(data, secret_values))
    if state in _BKASH_ENDED:
        return record_end(conn, payment["id"], _BKASH_ENDED[state], "bkash_" + state.lower(), scrub(data, secret_values))  # type: ignore[arg-type]
    return payment


def bkash_status(conn: Connection, payment: RowMapping, config: GatewayConfig | None = None) -> RowMapping:
    config = config or gateway_config(conn, "bkash")
    if config is None or not payment["gateway_session"]:
        return payment
    try:
        data = bkash.status(config, payment["gateway_session"])
    except GatewayError:
        logger.warning("bKash status unreachable: payment %s", payment["id"])
        return payment
    return _bkash_check(conn, payment, data, tuple(config.secrets.values()))


def confirm_bkash(conn: Connection, payment: RowMapping) -> RowMapping:
    config = gateway_config(conn, "bkash")
    if config is None or not payment["gateway_session"]:
        return payment
    secret_values = tuple(config.secrets.values())
    try:
        data = bkash.execute(config, payment["gateway_session"])
    except GatewayError:
        data = {}
    if data.get("transactionStatus"):
        return _bkash_check(conn, payment, data, secret_values)
    # Unclear answer or timeout: ask for the status.
    return bkash_status(conn, payment, config)


def refresh_initiated(conn: Connection, payment: RowMapping) -> RowMapping:
    """Before a new start: find out what happened to an earlier initiated payment."""
    if payment["method"] == "bkash":
        payment = bkash_status(conn, payment)
    if payment["status"] == "initiated":
        payment = record_end(conn, payment["id"], "abandoned", "abandoned", {"reason": "a new payment was started"})
    return payment
