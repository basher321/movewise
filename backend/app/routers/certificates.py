"""Certificates and completion letters (spec B20): view, PDF download, issue and send.

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.
Staff of the section (and the super admin) see drafts too; applicants only their own approved
certificate or issued letter; the public only through /certificates/{id} and the signed link.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.applications import notify_applicant, parse_id
from app.audit import Actor, write_audit
from app.auth.deps import Applicant, client_ip, current_applicant, ensure_licensed, get_current_actor, require_applicant, require_section
from app.catalog import parse_uuid
from app.certificates import service
from app.certificates.pdf import render
from app.db.engine import get_conn
from app.errors import ApiError, error_response, parse_body
from app.licence import MODULE_LABELS
from app.notify.outbox import queue_message
from app.routers.admin_applications import _load
from app.routers.enrolments import CHECKS_PER_MINUTE

router = APIRouter()

Channel = Literal["email", "whatsapp"]


class SendIn(BaseModel):
    channels: list[Channel] = Field(min_length=1, max_length=2)


def pdf_response(found: service.Found, download: bool) -> Response:
    disposition = "attachment" if download else "inline"
    return Response(
        content=render(found.doc),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{service.file_name(found)}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


def _channels(body: SendIn) -> tuple[str, ...]:
    return tuple(dict.fromkeys(body.channels))


def _send(conn: Connection, actor: Actor, found: service.Found, channels: tuple[str, ...]) -> int:
    person = conn.execute(
        text("SELECT name, email, phone FROM applicant_accounts WHERE id = :id"), {"id": found.applicant_id}
    ).one()
    what = "certificate" if found.kind == "certificate" else "completion letter"
    subject = f"Your {what} - {found.ref}"
    body = (
        f"Dear {person.name},\n\nPlease find your {what} for {found.view['title']} attached (ID {found.ref}).\n\n"
        "Anyone can check it on our website under Verify certificate."
    )
    whatsapp = f"Your {what} for {found.view['title']} (ID {found.ref}). Download it here: {service.download_link(found.ref)}"
    queued = queue_message(
        conn,
        person.name,
        person.email,
        person.phone or None,
        found.module,  # type: ignore[arg-type]
        f"{found.kind}_sent",
        subject,
        body,
        found.application_id,
        channels=channels,
        attachment=(found.kind, found.ref),
        whatsapp_body=whatsapp,
        sent_by=actor.id,
    )
    if queued == 0:
        raise ApiError("VALIDATION", 422, "This client has no email or phone number for the chosen channel.")
    write_audit(conn, actor, f"{found.kind}.sent", f"{found.ref} -> {', '.join(channels)}")
    return queued


# ---------------------------------------------------------------- course certificates (staff)


def _enrolment_found(conn: Connection, enrolment_id: str) -> service.Found:
    row = service.enrolment_row(conn, enrolment_id=parse_uuid(enrolment_id, "Enrolment"))
    if row is None:
        raise ApiError("NOT_FOUND", 404, "Enrolment not found.")
    if row["certificate_id"] is None:
        raise ApiError("CONFLICT", 409, "There is no certificate until the course is paid.")
    return service.course_found(conn, row)


@router.get("/admin/enrolments/{enrolment_id}/certificate")
def admin_certificate(
    enrolment_id: str, actor: Actor = Depends(require_section("course")), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _enrolment_found(conn, enrolment_id).view


@router.get("/admin/enrolments/{enrolment_id}/certificate.pdf")
def admin_certificate_pdf(
    enrolment_id: str,
    download: bool = False,
    actor: Actor = Depends(require_section("course")),
    conn: Connection = Depends(get_conn),
) -> Response:
    return pdf_response(_enrolment_found(conn, enrolment_id), download)


@router.post("/admin/enrolments/{enrolment_id}/certificate/send")
async def send_certificate(
    enrolment_id: str, request: Request, actor: Actor = Depends(require_section("course")), conn: Connection = Depends(get_conn)
) -> dict[str, int]:
    body = parse_body(SendIn, await request.body())
    found = _enrolment_found(conn, enrolment_id)
    if not found.view["valid"]:
        raise ApiError("CONFLICT", 409, "Approve the certificate before sending it.")
    return {"queued": _send(conn, actor, found, _channels(body))}


# ---------------------------------------------------------------- completion letters (staff)


def _case_found(conn: Connection, actor: Actor, app_id: str, lock: bool = False) -> service.Found:
    app = _load(conn, actor, app_id, lock=lock)
    row = service.case_row(conn, application_id=app["id"])
    assert row is not None
    return service.letter_found(conn, row)


@router.get("/admin/applications/{app_id}/letter", response_model=None)
def admin_letter(
    app_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any] | None:
    found = _case_found(conn, actor, app_id)
    return found.view if found.view["id"] else None


@router.get("/admin/applications/{app_id}/letter.pdf")
def admin_letter_pdf(
    app_id: str, download: bool = False, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> Response:
    return pdf_response(_case_found(conn, actor, app_id), download)


@router.post("/admin/applications/{app_id}/letter")
def issue_letter(
    app_id: str, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    app = _load(conn, actor, app_id, lock=True)
    if app["status"] != "completed":
        raise ApiError("CONFLICT", 409, "A completion letter can be issued only for a completed case.")
    if conn.execute(text("SELECT 1 FROM case_letters WHERE application_id = :id"), {"id": app["id"]}).first():
        raise ApiError("CONFLICT", 409, "The completion letter for this case is already issued.")
    letter_id = service.new_letter_id(conn)
    conn.execute(
        text("INSERT INTO case_letters (letter_id, application_id, issued_by) VALUES (:l, :a, :by)"),
        {"l": letter_id, "a": app["id"], "by": actor.id},
    )
    found = _case_found(conn, actor, app_id)
    notify_applicant(
        conn,
        app,
        "letter_ready",
        "Your completion letter is ready",
        f"Congratulations! Your completion letter for {found.view['title']} is ready. Letter ID: {letter_id}. "
        "You can download it in your profile.",
    )
    write_audit(conn, actor, "letter.issued", f"{letter_id} · {app['ref']} · {MODULE_LABELS[app['module']]}")
    return found.view


@router.post("/admin/applications/{app_id}/letter/send")
async def send_letter(
    app_id: str, request: Request, actor: Actor = Depends(get_current_actor), conn: Connection = Depends(get_conn)
) -> dict[str, int]:
    found = _case_found(conn, actor, app_id, lock=True)
    body = parse_body(SendIn, await request.body())
    if not found.view["id"]:
        raise ApiError("CONFLICT", 409, "Issue the completion letter before sending it.")
    if not found.view["valid"]:
        raise ApiError("CONFLICT", 409, "This letter is not valid while the case is not completed.")
    return {"queued": _send(conn, actor, found, _channels(body))}


# ---------------------------------------------------------------- the applicant's own


@router.get("/me/course/enrolments/{enrolment_id}/certificate.pdf")
def my_certificate_pdf(
    enrolment_id: str,
    download: bool = False,
    me: Applicant = Depends(require_applicant("course")),
    conn: Connection = Depends(get_conn),
) -> Response:
    row = service.enrolment_row(conn, enrolment_id=parse_uuid(enrolment_id, "Certificate"))
    if row is None or row["applicant_id"] != me.account["id"] or row["certificate_id"] is None:
        raise ApiError("NOT_FOUND", 404, "Certificate not found.")
    found = service.course_found(conn, row)
    if not found.view["valid"]:
        raise ApiError("NOT_FOUND", 404, "Certificate not found.")
    return pdf_response(found, download)


@router.get("/me/{module}/applications/{app_id}/letter.pdf")
def my_letter_pdf(
    module: str,
    app_id: str,
    download: bool = False,
    me: Applicant = Depends(current_applicant),
    conn: Connection = Depends(get_conn),
) -> Response:
    if module not in ("study", "job", "visa", "remote"):
        raise ApiError("NOT_FOUND", 404, "Not found.")
    row = service.case_row(conn, application_id=parse_id(app_id))
    if row is None or row["applicant_id"] != me.account["id"] or row["module"] != module or row["letter_id"] is None:
        raise ApiError("NOT_FOUND", 404, "Letter not found.")
    return pdf_response(service.letter_found(conn, row), download)


# ---------------------------------------------------------------- public signed link


@router.get("/certificates/{ref}/pdf", response_model=None)
def public_pdf(ref: str, request: Request, t: str = "", conn: Connection = Depends(get_conn)) -> Response:
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
    value = ref.strip().upper()[:20]
    found = service.find(conn, value) if service.check_token(value, t) else None
    if found is None or not found.view["valid"]:
        # Answered, not raised, so the rate_events row above is kept.
        return error_response("NOT_FOUND", "Certificate not found.")
    ensure_licensed(conn, found.module)  # type: ignore[arg-type]
    return pdf_response(found, download=True)
