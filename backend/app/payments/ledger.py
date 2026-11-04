"""The append-only ledger (spec B07 / F09)."""

import secrets
from datetime import date
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.licence import today_dhaka

Direction = Literal["in", "out"]

CATEGORY_LABELS: dict[str, str] = {
    "course": "Course fees",
    "study": "Student application fees",
    "job": "Job application fees",
    "visa": "Immigration application fees",
    "otherin": "Other income",
    "opening": "Opening balance",
    "salary": "Salaries",
    "rent": "Rent & utilities",
    "mkt": "Marketing",
    "partner": "Paid to universities / employers",
    "tools": "Software & tools",
    "refund": "Refunds",
    "otherout": "Other expenses",
}
CATEGORIES: dict[Direction, tuple[str, ...]] = {
    "in": ("course", "study", "job", "visa", "otherin", "opening"),
    "out": ("salary", "rent", "mkt", "partner", "tools", "refund", "otherout"),
}
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_INSERT = text(
    "INSERT INTO ledger_entries (ref, entry_date, direction, category, party, email, description, method, "
    "amount_poisha, auto, payment_id, reverses_id, created_by) VALUES (:ref, :entry_date, :direction, :category, "
    ":party, :email, :description, :method, :amount, :auto, :payment_id, :reverses_id, :created_by) RETURNING *"
)


def new_ref(conn: Connection) -> str:
    exists = text("SELECT 1 FROM ledger_entries WHERE ref = :ref")
    while True:
        ref = "LED-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(8))
        if conn.execute(exists, {"ref": ref}).first() is None:
            return ref


def add_entry(
    conn: Connection,
    *,
    direction: Direction,
    category: str,
    party: str,
    amount_poisha: int,
    auto: bool,
    email: str = "",
    description: str = "",
    method: str = "",
    entry_date: date | None = None,
    payment_id: Any = None,
    reverses_id: UUID | None = None,
    created_by: UUID | None = None,
) -> RowMapping:
    return conn.execute(
        _INSERT,
        {
            "ref": new_ref(conn),
            "entry_date": entry_date or today_dhaka(),
            "direction": direction,
            "category": category,
            "party": party,
            "email": email,
            "description": description,
            "method": method,
            "amount": amount_poisha,
            "auto": auto,
            "payment_id": payment_id,
            "reverses_id": reverses_id,
            "created_by": created_by,
        },
    ).mappings().one()
