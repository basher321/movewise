"""B20: certificates and completion letters - view, PDF, issue, send, verify (b159-b161, b164)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.certificates import service
from app.notify.worker import process_once
from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import course_body, group_body
from test_immigration import visa_body
from test_notify import FakeSMTP, run, set_up_email, set_up_whatsapp, smtp  # noqa: F401

ALL = ("course", "study", "job", "visa")
PHONE = "01712345678"


def is_pdf(response: Any) -> bool:
    return response.status_code == 200 and response.headers["content-type"] == "application/pdf" and response.content[:5] == b"%PDF-"


@pytest.fixture
def world(api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    group = client.post("/api/admin/course-groups", json=group_body()).json()
    course = client.post("/api/admin/courses", json=course_body(group["id"])).json()
    program = client.post("/api/admin/visa-programs", json=visa_body()).json()
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")

    learner = new_client(api)
    verified_applicant(learner, conn, "course", "learner@example.test")
    conn.execute(text("UPDATE applicant_accounts SET phone = :p WHERE module = 'course'"), {"p": PHONE})
    started = learner.post(
        "/api/me/course/enrolments", json={"course_slug": course["slug"], "method": "manual", "manual_ref": "C1", "phone": PHONE}
    ).json()
    finance.post(f"/api/admin/payments/{started['payment_id']}/verify")
    enrolment = learner.get("/api/me/course/enrolments").json()[0]

    traveller = new_client(api)
    verified_applicant(traveller, conn, "visa", "traveller@example.test")
    conn.execute(text("UPDATE applicant_accounts SET phone = :p WHERE module = 'visa'"), {"p": PHONE})
    app = traveller.post("/api/me/visa/applications", json={"item_slug": program["slug"], "answers": {}}).json()
    return {"learner": learner, "traveller": traveller, "finance": finance, "enrolment": enrolment, "app": app}


def complete(client: TestClient, app_id: str) -> None:
    assert client.post(f"/api/admin/applications/{app_id}/stage", json={"stage": 7, "note": "", "notify": False}).status_code == 200


# b159
def test_b159_course_certificate_view_and_download(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    eid = world["enrolment"]["id"]
    view = client.get(f"/api/admin/enrolments/{eid}/certificate").json()
    assert view["kind"] == "certificate" and view["id"].startswith("CERT-")
    assert (view["approved"], view["valid"]) == (False, False)
    draft = client.get(f"/api/admin/enrolments/{eid}/certificate.pdf")
    assert is_pdf(draft) and draft.headers["content-disposition"].startswith("inline")
    assert client.get(f"/api/admin/enrolments/{eid}/certificate.pdf?download=true").headers["content-disposition"].startswith("attachment")
    # The learner gets nothing before approval; finance never.
    assert world["learner"].get(f"/api/me/course/enrolments/{eid}/certificate.pdf").status_code == 404
    assert world["finance"].get(f"/api/admin/enrolments/{eid}/certificate.pdf").status_code == 403
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    assert staff.get(f"/api/admin/enrolments/{eid}/certificate").status_code == 403
    assert client.post(f"/api/admin/enrolments/{eid}/certificate/send", json={"channels": ["email"]}).status_code == 409

    client.post(f"/api/admin/enrolments/{eid}/approve-certificate")
    assert client.get(f"/api/admin/enrolments/{eid}/certificate").json()["valid"] is True
    assert is_pdf(world["learner"].get(f"/api/me/course/enrolments/{eid}/certificate.pdf"))
    other = new_client(api)
    verified_applicant(other, conn, "course", "other@example.test")
    assert other.get(f"/api/me/course/enrolments/{eid}/certificate.pdf").status_code == 404


# b160
def test_b160_completion_letter(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app_id = world["app"]["id"]
    assert client.get(f"/api/admin/applications/{app_id}/letter").json() is None
    assert is_pdf(client.get(f"/api/admin/applications/{app_id}/letter.pdf"))  # draft preview
    assert client.post(f"/api/admin/applications/{app_id}/letter").status_code == 409  # not completed
    complete(client, app_id)
    letter = client.post(f"/api/admin/applications/{app_id}/letter").json()
    assert letter["id"].startswith("LTR-") and letter["valid"] is True and letter["module"] == "visa"
    assert "Visitor Visa (Visit visa), Canada" == letter["subtitle"]
    assert client.post(f"/api/admin/applications/{app_id}/letter").status_code == 409  # once
    assert audit_count(conn, "letter.issued") == 1
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'letter_ready'")).scalar_one() == 2

    public = new_client(api)
    checked = public.get(f"/api/certificates/{letter['id'].lower()}").json()
    assert (checked["kind"], checked["valid"], checked["module"]) == ("letter", True, "visa")
    assert is_pdf(world["traveller"].get(f"/api/me/visa/applications/{app_id}/letter.pdf"))
    assert world["traveller"].get(f"/api/me/study/applications/{app_id}/letter.pdf").status_code in (401, 404)

    # Reopened: the letter is no longer valid, and cannot be sent.
    client.post(f"/api/admin/applications/{app_id}/status", json={"status": "active", "reason": "More documents"})
    assert public.get(f"/api/certificates/{letter['id']}").json()["valid"] is False
    assert client.post(f"/api/admin/applications/{app_id}/letter/send", json={"channels": ["email"]}).status_code == 409

    # Course certificates keep their old answer.
    assert public.get("/api/certificates/CERT-AAAAAAAA").status_code == 404


def test_letter_text_per_module() -> None:
    row: dict[str, Any] = {"module": "job", "v_title": "Welder", "v_employer": "Test Co", "v_country": "UAE"}
    assert service._case_item(row) == ("Welder", "Welder at Test Co, UAE")
    row = {"module": "study", "u_name": "Test University", "u_country": "Canada"}
    assert service._case_item(row) == ("Test University", "Test University, Canada")


# b161
def test_b161_send_with_attachment_and_signed_link(
    api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any], smtp: type[FakeSMTP], run: Any  # noqa: F811
) -> None:
    set_up_email(conn)
    set_up_whatsapp(conn)
    conn.execute(text("UPDATE applicant_accounts SET email = 'learner@example.test' WHERE module = 'course'"))
    eid = world["enrolment"]["id"]
    client.post(f"/api/admin/enrolments/{eid}/approve-certificate")
    conn.execute(text("UPDATE notifications SET status = 'sent' WHERE status = 'queued'"))
    sent = client.post(f"/api/admin/enrolments/{eid}/certificate/send", json={"channels": ["email", "whatsapp"]})
    assert sent.json() == {"queued": 2}
    assert audit_count(conn, "certificate.sent") == 1
    rows = conn.execute(
        text("SELECT channel, attachment_kind, attachment_ref, body, sent_by FROM notifications WHERE event = 'certificate_sent'")
    ).mappings().all()
    email = next(r for r in rows if r["channel"] == "email")
    wa = next(r for r in rows if r["channel"] == "whatsapp")
    cert_id = email["attachment_ref"]
    assert email["attachment_kind"] == "certificate" and email["sent_by"] is not None
    assert wa["attachment_kind"] is None and f"/api/certificates/{cert_id}/pdf?t=" in wa["body"]

    process_once(run)
    message = FakeSMTP.sent[-1]
    files = [p for p in message.iter_attachments()]
    assert [(p.get_filename(), p.get_content_type()) for p in files] == [(f"{cert_id}.pdf", "application/pdf")]
    assert files[0].get_content()[:5] == b"%PDF-"

    link = wa["body"].split("Download it here: ")[1].split()[0]
    path = link.split("/api", 1)[1]
    public = new_client(api)
    assert is_pdf(public.get("/api" + path))
    token = path.split("t=")[1]
    assert public.get(f"/api/certificates/{cert_id}/pdf?t={token[:-1]}0").status_code == 404
    expired = service.sign(cert_id, now=0)
    assert public.get(f"/api/certificates/{cert_id}/pdf?t={expired}").status_code == 404
    assert public.get(f"/api/certificates/{cert_id}/pdf").status_code == 404


def test_attachment_of_invalid_letter_is_never_sent(
    client: TestClient, conn: Connection, world: dict[str, Any], smtp: type[FakeSMTP], run: Any  # noqa: F811
) -> None:
    set_up_email(conn)
    conn.execute(text("UPDATE applicant_accounts SET email = 'traveller@example.test' WHERE module = 'visa'"))
    app_id = world["app"]["id"]
    complete(client, app_id)
    client.post(f"/api/admin/applications/{app_id}/letter")
    conn.execute(text("UPDATE notifications SET status = 'sent' WHERE status = 'queued'"))
    assert client.post(f"/api/admin/applications/{app_id}/letter/send", json={"channels": ["email"]}).json() == {"queued": 1}
    client.post(f"/api/admin/applications/{app_id}/status", json={"status": "active", "reason": "Reopened"})
    conn.execute(text("UPDATE notifications SET status = 'sent' WHERE status = 'queued' AND event <> 'letter_sent'"))
    process_once(run)
    status = conn.execute(text("SELECT status, last_error FROM notifications WHERE event = 'letter_sent'")).one()
    assert status[0] == "failed" and "no longer valid" in status[1]
    assert FakeSMTP.sent == []


# b164
def test_b164_letters_cannot_change(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app_id = world["app"]["id"]
    complete(client, app_id)
    client.post(f"/api/admin/applications/{app_id}/letter")
    for sql in ("UPDATE case_letters SET issued_at = now()", "DELETE FROM case_letters WHERE application_id = :id"):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql), {"id": app_id})


def test_pdf_handles_bangla_name_and_logo(conn: Connection) -> None:
    from app.certificates.pdf import CertDoc, render

    data = render(CertDoc("Certificate of Completion", "This is to certify that", "রানা আহমেদ", "line", "Title", "sub",
                          "Issued 1 January 2027", "Certificate ID CERT-AAAAAAAA", "Company", None, True))
    assert data[:5] == b"%PDF-"
    broken_logo = render(CertDoc("H", "i", "Name", "l", "T", "", "Issued", "id", "Company", b"not an image", False))
    assert broken_logo[:5] == b"%PDF-"
