"""Enquiries from the Contact page and their follow-up (spec B09).

Public: a hidden "website" honeypot (filled -> answer 200, save nothing), 5 enquiries per IP per
hour, and the same name + contact + message within 2 minutes saved once. Staff: admin or
super admin (never finance). Notes are added, never changed or removed.
"""

import re
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.deps import client_ip, get_current_actor
from app.db.engine import get_conn
from app.errors import ApiError, parse_body
from app.licence import MODULE_LABELS, read_licence, today_dhaka
from app.notify.outbox import queue_message

router = APIRouter()

PAGE_SIZE = 50
PER_HOUR = 5
STATUSES = ("new", "contacted", "converted", "closed")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_PHONE = re.compile(r"(?:(?:\+?88)?01[3-9]\d{8}|\+[1-9]\d{7,14})")


def _invalid(message: str) -> ApiError:
    return ApiError("VALIDATION", 422, message)


def _staff(actor: Actor = Depends(get_current_actor)) -> Actor:
    if actor.role not in ("super_admin", "admin"):
        raise ApiError("FORBIDDEN", 403, "Only admins can work with enquiries.")
    return actor


def _check(conn: Connection, name: str, contact: str, interest: str, message: str) -> tuple[str, str, str]:
    name, contact, message = name.strip(), contact.strip(), message.strip()
    if not name:
        raise _invalid("Please enter your name.")
    if len(name) > 120:
        raise _invalid("Name must be at most 120 characters.")
    compact = re.sub(r"[\s-]", "", contact)
    if not contact:
        raise _invalid("Please enter your email or phone number.")
    if not (_EMAIL.fullmatch(contact) or _PHONE.fullmatch(compact)):
        raise _invalid("Please enter a valid email or phone number.")
    licence = read_licence(conn)
    if interest != "other" and not (interest in MODULE_LABELS and licence.licensed(interest)):  # type: ignore[arg-type]
        raise _invalid("Please choose what you are interested in.")
    if len(message) > 2000:
        raise _invalid("Message must be at most 2,000 characters.")
    return name, contact, message


# ---------------------------------------------------------------- public


class PublicIn(BaseModel):
    name: str = Field(max_length=1000)
    contact: str = Field(max_length=300)
    interest: str = Field(max_length=20)
    preferred_date: date | None = None
    message: str = Field(default="", max_length=10_000)
    website: str = Field(default="", max_length=1000)


@router.post("/enquiries")
async def submit_enquiry(request: Request, conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    body = parse_body(PublicIn, await request.body())
    if body.website.strip():
        return {"ok": True}  # honeypot: a bot filled the hidden field
    name, contact, message = _check(conn, body.name, body.contact, body.interest, body.message)
    if body.preferred_date is not None and body.preferred_date < today_dhaka():
        raise _invalid("The preferred date cannot be in the past.")
    ip = client_ip(request) or "unknown"
    conn.execute(text("SELECT pg_advisory_xact_lock(3000010, hashtext(:ip))"), {"ip": ip})
    duplicate = conn.execute(
        text(
            "SELECT 1 FROM enquiries WHERE name = :n AND contact = :c AND message = :m "
            "AND created_at > clock_timestamp() - interval '2 minutes'"
        ),
        {"n": name, "c": contact, "m": message},
    ).first()
    if duplicate is not None:
        return {"ok": True}
    recent = conn.execute(
        text("SELECT count(*) FROM enquiries WHERE ip = :ip AND created_at > clock_timestamp() - interval '1 hour'"),
        {"ip": ip},
    ).scalar_one()
    if int(recent) >= PER_HOUR:
        raise ApiError("TOO_MANY_TRIES", 429, "Too many enquiries. Please try again later or call us.")
    conn.execute(
        text(
            "INSERT INTO enquiries (name, contact, interest, preferred_date, message, ip, created_at) "
            "VALUES (:n, :c, :i, :d, :m, :ip, clock_timestamp())"
        ),
        {"n": name, "c": contact, "i": body.interest, "d": body.preferred_date, "m": message, "ip": ip},
    )
    company = conn.execute(text("SELECT name, email FROM settings WHERE singleton = 'settings'")).one()
    if company.email:
        interest = "Other" if body.interest == "other" else MODULE_LABELS[body.interest]  # type: ignore[index]
        lines = [f"Name: {name}", f"Contact: {contact}", f"Interested in: {interest}"]
        if body.preferred_date:
            lines.append(f"Preferred date: {body.preferred_date.isoformat()}")
        if message:
            lines.append(f"\n{message}")
        queue_message(conn, company.name, company.email, None, None, "new_enquiry", f"New enquiry from {name}", "\n".join(lines))
    write_audit(conn, Actor(id=None, name="Visitor", role=None, ip=ip), "enquiry.received", f"{name} · {body.interest}")
    return {"ok": True}


# ---------------------------------------------------------------- staff

_NOTES = text(
    "SELECT * FROM enquiry_notes WHERE enquiry_id IN :ids ORDER BY at, id"
).bindparams(bindparam("ids", expanding=True))
_SELECT = (
    "SELECT q.*, a.name AS assigned_name, a.active AS assigned_active FROM enquiries q "
    "LEFT JOIN admin_users a ON a.id = q.assigned_to "
)


def _views(conn: Connection, rows: list[RowMapping]) -> list[dict[str, Any]]:
    notes: dict[Any, list[dict[str, Any]]] = {r["id"]: [] for r in rows}
    if rows:
        for n in conn.execute(_NOTES, {"ids": list(notes)}).mappings():
            notes[n["enquiry_id"]].append({"id": str(n["id"]), "at": n["at"].isoformat(), "by": n["by_name"], "text": n["text"]})
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "contact": r["contact"],
            "interest": r["interest"],
            "preferred_date": r["preferred_date"].isoformat() if r["preferred_date"] else None,
            "message": r["message"],
            "status": r["status"],
            "assigned_to": None
            if r["assigned_to"] is None
            else {
                "id": str(r["assigned_to"]),
                "name": r["assigned_name"] if r["assigned_active"] else f"{r['assigned_name']} (deactivated)",
            },
            "created_at": r["created_at"].isoformat(),
            "notes": notes[r["id"]],
        }
        for r in rows
    ]


def _one(conn: Connection, enquiry_id: Any) -> dict[str, Any]:
    return _views(conn, [conn.execute(text(_SELECT + "WHERE q.id = :id"), {"id": enquiry_id}).mappings().one()])[0]


def _lock(conn: Connection, enquiry_id: str) -> RowMapping:
    try:
        uid = UUID(enquiry_id)
    except ValueError:
        raise ApiError("NOT_FOUND", 404, "Enquiry not found.") from None
    row = conn.execute(text("SELECT * FROM enquiries WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Enquiry not found.")
    return row


@router.get("/admin/enquiries")
def list_enquiries(
    status: str = "", q: str = "", page: int = 1, actor: Actor = Depends(_staff), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    where = ["TRUE"]
    params: dict[str, Any] = {}
    if status:
        if status not in STATUSES:
            raise _invalid("Unknown status.")
        where.append("q.status = :status")
        params["status"] = status
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where.append("(q.name ILIKE :q OR q.contact ILIKE :q OR q.message ILIKE :q)")
    if page < 1:
        raise _invalid("Page must be 1 or more.")
    clause = " WHERE " + " AND ".join(where)
    total = int(conn.execute(text("SELECT count(*) FROM enquiries q" + clause), params).scalar_one())
    rows = list(
        conn.execute(
            text(_SELECT + clause + " ORDER BY q.created_at DESC, q.id LIMIT :l OFFSET :o"),
            {**params, "l": PAGE_SIZE, "o": (page - 1) * PAGE_SIZE},
        ).mappings()
    )
    return {"items": _views(conn, rows), "total": total, "page": page, "page_size": PAGE_SIZE}


class StaffIn(BaseModel):
    name: str = Field(max_length=1000)
    contact: str = Field(max_length=300)
    interest: str = Field(max_length=20)
    message: str = Field(default="", max_length=10_000)


@router.post("/admin/enquiries")
async def add_enquiry(request: Request, actor: Actor = Depends(_staff), conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    body = parse_body(StaffIn, await request.body())
    name, contact, message = _check(conn, body.name, body.contact, body.interest, body.message)
    new_id = conn.execute(
        text("INSERT INTO enquiries (name, contact, interest, message) VALUES (:n, :c, :i, :m) RETURNING id"),
        {"n": name, "c": contact, "i": body.interest, "m": message},
    ).scalar_one()
    write_audit(conn, actor, "enquiry.added", f"{name} · {body.interest}")
    return _one(conn, new_id)


class PatchIn(BaseModel):
    status: str | None = None
    assigned_to: str | None = None


@router.patch("/admin/enquiries/{enquiry_id}")
async def update_enquiry(
    enquiry_id: str, request: Request, actor: Actor = Depends(_staff), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _lock(conn, enquiry_id)
    body = parse_body(PatchIn, await request.body())
    values: dict[str, Any] = {}
    if "status" in body.model_fields_set:
        if body.status not in STATUSES:
            raise _invalid("Please choose a status.")
        values["status"] = body.status
    if "assigned_to" in body.model_fields_set:
        if body.assigned_to is None:
            values["assigned_to"] = None
        else:
            try:
                uid = UUID(body.assigned_to)
            except ValueError:
                raise _invalid("Please choose an admin.") from None
            staff = conn.execute(
                text("SELECT role, approved, active FROM admin_users WHERE id = :id"), {"id": uid}
            ).one_or_none()
            if staff is None or not staff.approved or not staff.active or staff.role == "finance":
                raise _invalid("Please choose an admin.")
            values["assigned_to"] = uid
    changed = [k for k, v in values.items() if row[k] != v]
    if changed:
        sets = ", ".join(f"{k} = :{k}" for k in changed)
        conn.execute(text(f"UPDATE enquiries SET {sets} WHERE id = :id"), {**{k: values[k] for k in changed}, "id": row["id"]})
        write_audit(conn, actor, "enquiry.updated", f"{row['name']}: {', '.join(changed)}")
    return _one(conn, row["id"])


class NoteIn(BaseModel):
    text: str = Field(max_length=5000)


@router.post("/admin/enquiries/{enquiry_id}/notes")
async def add_note(
    enquiry_id: str, request: Request, actor: Actor = Depends(_staff), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    row = _lock(conn, enquiry_id)
    note = parse_body(NoteIn, await request.body()).text.strip()
    if not note:
        raise _invalid("Please write the note.")
    if len(note) > 2000:
        raise _invalid("A note must be at most 2,000 characters.")
    conn.execute(
        text("INSERT INTO enquiry_notes (enquiry_id, by_id, by_name, text) VALUES (:e, :by, :name, :t)"),
        {"e": row["id"], "by": actor.id, "name": actor.name, "t": note},
    )
    write_audit(conn, actor, "enquiry.note", row["name"])
    return _one(conn, row["id"])
