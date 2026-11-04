"""Invoices (spec B07): gap-free numbers <invoice_prefix>-<year>-<4 digits> and a snapshot of
the company details at issue time."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.licence import today_dhaka

# The counter row is locked by this statement until the transaction ends, so two payments
# can never get the same number, and a rolled-back payment gives its number back (no gaps).
_NEXT = text(
    "INSERT INTO invoice_counters (year, last_no) VALUES (:year, 1) "
    "ON CONFLICT (year) DO UPDATE SET last_no = invoice_counters.last_no + 1 RETURNING last_no"
)
_COMPANY = text(
    "SELECT name, address, email, vat_bin, invoice_footer, invoice_prefix FROM settings WHERE singleton = 'settings'"
)
_INSERT = text(
    "INSERT INTO invoices (no, payment_id, applicant_id, module, name, email, description, method, amount_poisha, "
    "company_name, company_address, company_email, vat_bin, footer) VALUES (:no, :payment_id, :applicant_id, "
    ":module, :name, :email, :description, :method, :amount, :company_name, :company_address, :company_email, "
    ":vat_bin, :footer) RETURNING *"
)

METHOD_LABELS = {"sslcommerz": "SSLCommerz", "bkash": "bKash", "manual": "Bank transfer / office"}


def issue_invoice(conn: Connection, payment: RowMapping) -> RowMapping:
    company = conn.execute(_COMPANY).one()
    year = today_dhaka().year
    number = int(conn.execute(_NEXT, {"year": year}).scalar_one())
    person = conn.execute(
        text("SELECT name, email FROM applicant_accounts WHERE id = :id"), {"id": payment["applicant_id"]}
    ).one()
    return conn.execute(
        _INSERT,
        {
            "no": f"{company.invoice_prefix}-{year}-{number:04d}",
            "payment_id": payment["id"],
            "applicant_id": payment["applicant_id"],
            "module": payment["module"],
            "name": person.name,
            "email": person.email or "",
            "description": payment["purpose"],
            "method": METHOD_LABELS[payment["method"]],
            "amount": payment["amount_poisha"],
            "company_name": company.name,
            "company_address": company.address,
            "company_email": company.email,
            "vat_bin": company.vat_bin,
            "footer": company.invoice_footer,
        },
    ).mappings().one()


def invoice_view(row: RowMapping, email_status: str | None = None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "no": row["no"],
        "module": row["module"],
        "name": row["name"],
        "email": row["email"],
        "description": row["description"],
        "method": row["method"],
        "amount_poisha": int(row["amount_poisha"]),
        "issued_at": row["issued_at"].isoformat(),
        "company": {
            "name": row["company_name"],
            "address": row["company_address"],
            "email": row["company_email"],
            "vat_bin": row["vat_bin"],
            "footer": row["footer"],
        },
        "status": "refunded" if row["refunded"] else "paid",
        "refunded_at": row["refunded_at"].isoformat() if row["refunded_at"] else None,
    }
    if email_status is not None:
        view["email_status"] = email_status
    return view
