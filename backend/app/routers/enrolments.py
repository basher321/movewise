"""Course enrolments, certificates and the public certificate check (spec B09).

Enrolments are paid through the B07 payment service: on_paid makes the enrolment active with a
certificate id; on_refunded cancels it. A certificate is valid only when approved and not
cancelled.
"""

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from app.audit import Actor, write_audit
from app.auth.deps import Applicant, client_ip, require_applicant, require_module, require_section
from app.db.engine import get_conn
from app.catalog import parse_uuid
from app.errors import ApiError, error_response, parse_body
from app.licence import read_licence
from app.payments.service import money_text, notify_person, register_on_paid, register_on_refunded
from app.routers import finance
from app.routers.pay import PayIn, start_payment

router = APIRouter()

ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAGE_SIZE = 50
CHECKS_PER_MINUTE = 60
ENROL_LOCK = 3_000_009


class EnrolIn(PayIn):
    course_slug: str = Field(max_length=200)


def _new_code(conn: Connection, column: str, prefix: str, length: int) -> str:
    exists = text(f"SELECT 1 FROM enrolments WHERE {column} = :v")
    while True:
        value = prefix + "".join(secrets.choice(ID_ALPHABET) for _ in range(length))
        if conn.execute(exists, {"v": value}).first() is None:
            return value


# ---------------------------------------------------------------- payment hooks


def _enrolment_paid(conn: Connection, payment: RowMapping) -> None:
    enrolment = conn.execute(
        text("SELECT e.*, c.title FROM enrolments e JOIN courses c ON c.id = e.course_id WHERE e.id = :id FOR UPDATE"),
        {"id": payment["ref_id"]},
    ).mappings().one()
    if enrolment["status"] != "awaiting_payment":
        return
    conn.execute(
        text("UPDATE enrolments SET status = 'active', certificate_id = :c WHERE id = :id"),
        {"c": _new_code(conn, "certificate_id", "CERT-", 8), "id": enrolment["id"]},
    )
    notify_person(
        conn,
        enrolment["applicant_id"],
        "course",
        "enrolled",
        f"You are enrolled in {enrolment['title']}",
        f"Welcome! Your enrolment in {enrolment['title']} (order {enrolment['order_no']}) is confirmed. "
        "You can see it in your profile.",
    )


def _enrolment_refunded(conn: Connection, payment: RowMapping) -> None:
    conn.execute(text("UPDATE enrolments SET status = 'cancelled' WHERE id = :id"), {"id": payment["ref_id"]})


register_on_paid("enrolment", _enrolment_paid)
register_on_refunded("enrolment", _enrolment_refunded)


def _unpaid_enrolments(conn: Connection, applicant_id: Any) -> list[dict[str, Any]]:
    if not read_licence(conn).licensed("course"):
        return []
    rows = conn.execute(
        text(
            "SELECT e.id, e.order_no, e.price_poisha, e.applicant_id, c.title, p.name, p.email, p.phone, "
            "(SELECT pay.status FROM payments pay WHERE pay.ref_type = 'enrolment' AND pay.ref_id = e.id "
            " AND pay.status IN ('initiated', 'pending_verify') ORDER BY pay.created_at DESC LIMIT 1) AS live "
            "FROM enrolments e JOIN courses c ON c.id = e.course_id JOIN applicant_accounts p ON p.id = e.applicant_id "
            "WHERE e.status = 'awaiting_payment' AND (CAST(:a AS uuid) IS NULL OR e.applicant_id = :a) "
            "ORDER BY e.created_at, e.id"
        ),
        {"a": applicant_id},
    ).mappings()
    return [
        {
            "applicant_id": str(r["applicant_id"]),
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "module": "course",
            "ref_type": "enrolment",
            "ref_id": str(r["id"]),
            "ref": r["order_no"],
            "purpose": f"Course - {r['title']} ({r['order_no']})",
            "status": "pending_verify" if r["live"] == "pending_verify" else "unpaid",
            "amount_poisha": int(r["price_poisha"]),
        }
        for r in rows
    ]


if _unpaid_enrolments not in finance.EXTRA_OUTSTANDING:
    finance.EXTRA_OUTSTANDING.append(_unpaid_enrolments)


# ---------------------------------------------------------------- views

_SELECT = (
    "SELECT e.*, c.title, c.slug, c.duration, c.level, c.icon, c.colour, "
    "p.name AS p_name, p.email AS p_email, p.public_id AS p_public_id, "
    "(SELECT row_to_json(x) FROM (SELECT pay.status, pay.method FROM payments pay WHERE pay.ref_type = 'enrolment' "
    " AND pay.ref_id = e.id ORDER BY pay.created_at DESC LIMIT 1) x) AS last_payment "
    "FROM enrolments e JOIN courses c ON c.id = e.course_id JOIN applicant_accounts p ON p.id = e.applicant_id "
)


def _view(row: RowMapping, staff: bool = False) -> dict[str, Any]:
    payment = row["last_payment"] or {}
    has_certificate = row["status"] in ("active", "completed")
    view: dict[str, Any] = {
        "id": str(row["id"]),
        "order_no": row["order_no"],
        "course": {
            "slug": row["slug"],
            "title": row["title"],
            "duration": row["duration"],
            "level": row["level"],
            "icon": row["icon"],
            "colour": row["colour"],
        },
        "price_poisha": int(row["price_poisha"]),
        "status": row["status"],
        "payment_status": payment.get("status"),
        "method": payment.get("method"),
        "enrolled_at": row["created_at"].isoformat(),
        "certificate_id": row["certificate_id"] if has_certificate else None,
        "certificate_approved": row["certificate_approved"],
        "certificate_approved_at": row["certificate_approved_at"].isoformat() if row["certificate_approved_at"] else None,
    }
    if staff:
        view["learner"] = {"name": row["p_name"], "email": row["p_email"], "public_id": row["p_public_id"]}
    return view


# ---------------------------------------------------------------- learner


@router.post("/me/course/enrolments")
async def enrol(
    request: Request, me: Applicant = Depends(require_applicant("course")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    body = parse_body(EnrolIn, await request.body())
    course = conn.execute(
        text("SELECT * FROM courses WHERE slug = :s AND published"), {"s": body.course_slug.strip()}
    ).mappings().one_or_none()
    if course is None:
        raise ApiError("NOT_FOUND", 404, "Course not found.")
    applicant_id = me.account["id"]
    conn.execute(text("SELECT pg_advisory_xact_lock(:a, hashtext(:b))"), {"a": ENROL_LOCK, "b": str(applicant_id)})
    existing = conn.execute(
        text("SELECT * FROM enrolments WHERE applicant_id = :a AND course_id = :c AND status <> 'cancelled' FOR UPDATE"),
        {"a": applicant_id, "c": course["id"]},
    ).mappings().one_or_none()
    if existing is not None and existing["status"] in ("active", "completed"):
        raise ApiError("CONFLICT", 409, "You already have this course.")
    if existing is not None:
        waiting = conn.execute(
            text(
                "SELECT 1 FROM payments WHERE ref_type = 'enrolment' AND ref_id = :id "
                "AND status IN ('paid', 'pending_verify')"
            ),
            {"id": existing["id"]},
        ).first()
        if waiting is not None:
            raise ApiError("CONFLICT", 409, "A payment for this course is waiting for verification.")
        enrolment = existing
    else:
        enrolment = conn.execute(
            text(
                "INSERT INTO enrolments (order_no, applicant_id, course_id, price_poisha) "
                "VALUES (:o, :a, :c, :p) RETURNING *"
            ),
            {"o": _new_code(conn, "order_no", "ORD-", 6), "a": applicant_id, "c": course["id"], "p": course["price_poisha"]},
        ).mappings().one()
    purpose = f"Course - {course['title']} ({enrolment['order_no']})"
    # The price was locked when the enrolment was created; start_payment writes the audit row.
    started = start_payment(
        conn, me, "course", "enrolment", enrolment["id"], purpose, int(enrolment["price_poisha"]), body
    )
    row = conn.execute(text(_SELECT + "WHERE e.id = :id"), {"id": enrolment["id"]}).mappings().one()
    return {"enrolment": _view(row), **started}


@router.get("/me/course/enrolments")
def my_enrolments(
    me: Applicant = Depends(require_applicant("course")), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(_SELECT + "WHERE e.applicant_id = :a ORDER BY e.created_at DESC, e.id"), {"a": me.account["id"]}
    ).mappings()
    return [_view(r) for r in rows]


# ---------------------------------------------------------------- staff


@router.get("/admin/enrolments")
def list_enrolments(
    q: str = "",
    status: str = "",
    page: int = 1,
    actor: Actor = Depends(require_section("course")),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:
    where = ["TRUE"]
    params: dict[str, Any] = {}
    if status:
        if status not in ("awaiting_payment", "active", "completed", "cancelled"):
            raise ApiError("VALIDATION", 422, "Unknown status.")
        where.append("e.status = :status")
        params["status"] = status
    search = q.strip()[:100]
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        where.append(
            "(p.name ILIKE :q OR p.email ILIKE :q OR p.public_id ILIKE :q OR c.title ILIKE :q "
            "OR e.order_no ILIKE :q OR COALESCE(e.certificate_id, '') ILIKE :q)"
        )
    if page < 1:
        raise ApiError("VALIDATION", 422, "Page must be 1 or more.")
    clause = " WHERE " + " AND ".join(where)
    total = int(
        conn.execute(
            text(
                "SELECT count(*) FROM enrolments e JOIN courses c ON c.id = e.course_id "
                "JOIN applicant_accounts p ON p.id = e.applicant_id" + clause
            ),
            params,
        ).scalar_one()
    )
    rows = conn.execute(
        text(_SELECT + clause + " ORDER BY e.created_at DESC, e.id LIMIT :l OFFSET :o"),
        {**params, "l": PAGE_SIZE, "o": (page - 1) * PAGE_SIZE},
    ).mappings()
    return {"items": [_view(r, staff=True) for r in rows], "total": total, "page": page, "page_size": PAGE_SIZE}


@router.post("/admin/enrolments/{enrolment_id}/approve-certificate")
def approve_certificate(
    enrolment_id: str, actor: Actor = Depends(require_section("course")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    uid = parse_uuid(enrolment_id, "Enrolment")
    row = conn.execute(text("SELECT * FROM enrolments WHERE id = :id FOR UPDATE"), {"id": uid}).mappings().one_or_none()
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Enrolment not found.")
    if row["status"] not in ("active", "completed") or row["certificate_approved"]:
        raise ApiError("CONFLICT", 409, "This certificate cannot be approved now.")
    conn.execute(
        text(
            "UPDATE enrolments SET status = 'completed', certificate_approved = true, certificate_approved_by = :by, "
            "certificate_approved_at = now() WHERE id = :id"
        ),
        {"by": actor.id, "id": uid},
    )
    full = conn.execute(text(_SELECT + "WHERE e.id = :id"), {"id": uid}).mappings().one()
    notify_person(
        conn,
        row["applicant_id"],
        "course",
        "certificate_ready",
        "Your certificate is ready",
        f"Congratulations! Your certificate for {full['title']} is ready. Certificate ID: {row['certificate_id']}. "
        "You can open it in your profile.",
    )
    write_audit(conn, actor, "certificate.approved", f"{row['certificate_id']} · {full['title']} · {full['p_public_id']}")
    return _view(full, staff=True)


# ---------------------------------------------------------------- public certificate check


@router.get("/certificates/{certificate_id}", dependencies=[Depends(require_module("course"))], response_model=None)
def check_certificate(
    certificate_id: str, request: Request, conn: Connection = Depends(get_conn)
) -> dict[str, Any] | JSONResponse:
    ip = client_ip(request) or "unknown"
    recent = conn.execute(
        text(
            "SELECT count(*) FROM rate_events WHERE kind = 'certificate_check' AND ip = :ip "
            "AND at > clock_timestamp() - interval '1 minute'"
        ),
        {"ip": ip},
    ).scalar_one()
    if int(recent) >= CHECKS_PER_MINUTE:
        raise ApiError("TOO_MANY_TRIES", 429, "Too many checks. Please wait a minute.")
    conn.execute(text("INSERT INTO rate_events (kind, ip) VALUES ('certificate_check', :ip)"), {"ip": ip})
    row = conn.execute(
        text(
            "SELECT p.name, c.title, c.duration, c.level, e.certificate_approved_at FROM enrolments e "
            "JOIN courses c ON c.id = e.course_id JOIN applicant_accounts p ON p.id = e.applicant_id "
            "WHERE e.certificate_id = :id AND e.certificate_approved AND e.status <> 'cancelled'"
        ),
        {"id": certificate_id.strip().upper()[:20]},
    ).mappings().one_or_none()
    if row is None:
        # Answered, not raised: raising would roll back the rate_events row above, and then
        # guessing certificate ids would never be limited.
        return error_response("NOT_FOUND", "Certificate not found.")
    return {
        "valid": True,
        "name": row["name"],
        "course_title": row["title"],
        "duration": row["duration"],
        "level": row["level"],
        "issued_at": row["certificate_approved_at"].isoformat(),
    }
