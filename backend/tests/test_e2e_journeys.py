"""End-to-end user journeys through the real API (B19 check of the whole system).

Every journey runs inside the test transaction (rolled back), against movewise_test only.
People: a visitor, an applicant per module, the super admin, a section admin and finance.
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import PASSWORD, license_modules, sign_in_admin_on, signin_applicant, verified_applicant
from conftest import new_client
from test_catalog import course_body, group_body, university_body, vacancy_body
from test_immigration import visa_body

ALL = ("course", "study", "job", "visa")
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def upload(client: TestClient, module: str, app_id: str, doc_type: str) -> Any:
    return ok(
        client.post(
            f"/api/me/{module}/applications/{app_id}/documents",
            data={"type": doc_type},
            files={"file": ("file.pdf", PDF, "application/pdf")},
        )
    )


def pay_manual_and_verify(client: TestClient, finance: TestClient, module: str, app_id: str, ref: str) -> None:
    started = ok(client.post(f"/api/me/{module}/applications/{app_id}/pay", json={"method": "manual", "manual_ref": ref, "phone": "01712345678"}))
    assert started["status"] == "pending_verify"
    pending = ok(finance.get("/api/admin/payments/pending"))
    assert any(p["id"] == started["payment_id"] for p in pending)
    assert ok(finance.post(f"/api/admin/payments/{started['payment_id']}/verify"))["status"] == "paid"


def ledger_categories(conn: Connection) -> list[str]:
    return [r[0] for r in conn.execute(text("SELECT category FROM ledger_entries ORDER BY created_at, id"))]


def test_journey_immigration_applicant_and_staff(
    api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    license_modules(conn, *ALL)
    act_as("super_admin")

    # Super admin: programme, agent, partner, fee.
    program = ok(client.post("/api/admin/visa-programs", json=visa_body()))
    ok(client.post("/api/admin/visa-programs", json=visa_body(title="Spouse Visa", country="UK", visa_type="spouse")))
    agent = ok(
        client.post(
            "/api/admin/agents",
            json={
                "name": "Dhaka Visa Agent", "firm": "", "phone": "", "email": "", "country": "", "address": "",
                "sections": ["visa"], "commission_type": "fixed", "commission_poisha": 300000,
                "commission_percent_bp": 0, "notes": "", "active": True,
            },
        )
    )
    ok(
        client.post(
            "/api/admin/partners",
            json={
                "module": "visa", "partner_type": "law_firm", "name": "Test Immigration Law", "country": "Canada",
                "website": "https://law.example.test", "description": "", "contact_name": "Private", "contact_email": "",
                "contact_phone": "", "agreement_ref": "SECRET", "agreement_until": None, "show_on_site": True,
                "sort_order": 0, "active": True,
            },
        )
    )
    ok(client.put("/api/admin/fees", json={"visa": {program["id"]: 500000}}))

    # Visitor: page data, options, matching, agent answer, partners, enquiry.
    visitor = new_client(api)
    assert ok(visitor.get("/api/licence"))["modules"]["visa"] is True
    assert {p["title"] for p in ok(visitor.get("/api/visa-programs"))} == {"Visitor Visa", "Spouse Visa"}
    options = ok(visitor.get("/api/catalog/options"))
    assert options["visa_types"] == ["visit", "spouse"]
    match = ok(visitor.post("/api/match/visa", json={"country": "UK", "visa_type": "spouse", "passport_ready": True}))
    assert [m["item"]["title"] for m in match] == ["Spouse Visa"]
    answer = ok(
        visitor.post(
            "/api/agent/visa/ask",
            json={"question": "Which documents do I need?", "inputs": {"country": "Canada", "visa_type": "visit", "passport_ready": True}},
        )
    )["answer"]
    assert "Passport" in answer
    partners = ok(visitor.get("/api/partners?module=visa"))
    assert [p["name"] for p in partners] == ["Test Immigration Law"]
    assert "agreement_ref" not in partners[0]
    assert ok(visitor.post("/api/enquiries", json={"name": "Rana", "contact": "01712345678", "interest": "visa", "message": "UK visa?"}))

    # Applicant: sign up, apply, pay, upload, follow the case.
    applicant = new_client(api)
    verified_applicant(applicant, conn, "visa", "rana@example.test")
    app = ok(applicant.post("/api/me/visa/applications", json={"item_slug": program["slug"], "answers": {"country": "Canada", "passport_ready": True}}))
    assert app["fee_poisha"] == 500000
    assert app["missing_count"] == 7

    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    pay_manual_and_verify(applicant, finance, "visa", app["id"], "BANK-VISA-1")
    detail = ok(applicant.get(f"/api/me/visa/applications/{app['id']}"))
    assert detail["fee_paid"] is True and detail["invoice"] is not None
    assert "visa" in ledger_categories(conn)
    assert ok(applicant.get("/api/me/visa/invoices"))

    doc = upload(applicant, "visa", app["id"], "Valid passport (all pages)")
    passport = doc
    assert passport["type"] == "Valid passport (all pages)" and passport["status"] == "pending"

    # Visa section admin handles the case.
    staff = new_client(api)
    staff_id, _ = sign_in_admin_on(staff, conn, "admin", ["visa"])
    assert staff.get("/api/admin/applications?module=study").status_code == 403
    assert ok(staff.post(f"/api/admin/documents/{passport['id']}/verify", json={"expiry": None}))["status"] == "verified"
    ok(staff.patch(f"/api/admin/applications/{app['id']}", json={"assigned_to": str(staff_id), "interview_at": "2027-01-10T10:00:00", "deadline": "2026-12-31"}))
    for stage in (1, 2, 3, 4, 5):
        ok(staff.post(f"/api/admin/applications/{app['id']}/stage", json={"stage": stage, "note": "", "notify": True}))
    ok(staff.post(f"/api/admin/applications/{app['id']}/status", json={"status": "on_hold", "reason": "Waiting for bank letter"}))
    ok(staff.post(f"/api/admin/applications/{app['id']}/status", json={"status": "active", "reason": ""}))
    ok(staff.post(f"/api/admin/applications/{app['id']}/notes", json={"note": "Embassy slot booked"}))
    ok(staff.post(f"/api/admin/applications/{app['id']}/email", json={"to": "provider", "subject": "File", "body": "Attached"}))
    ok(staff.put(f"/api/admin/applications/{app['id']}/agent", json={"agent_id": agent["id"]}))
    done = ok(staff.post(f"/api/admin/applications/{app['id']}/stage", json={"stage": 7, "note": "Visa granted", "notify": True}))
    assert done["status"] == "completed"

    mine = ok(applicant.get(f"/api/me/visa/applications/{app['id']}"))
    assert mine["advisor_name"] and mine["interview_at"]
    texts = [e["text"] for e in mine["history"]]
    assert "Stage -> Ready to travel ✈" in texts and "Internal note" not in texts
    sent = conn.execute(
        text("SELECT count(*) FROM notifications WHERE application_id = :id AND event = 'stage_changed'"), {"id": app["id"]}
    ).scalar_one()
    assert sent >= 6

    # Finance pays the agent commission.
    commission = ok(finance.get("/api/admin/agents/commissions?module=visa"))[0]
    assert commission["amount_poisha"] == 300000
    assert ok(finance.post(f"/api/admin/agents/commissions/{commission['id']}/pay", json={"pay_reference": "BK-1"}))["status"] == "paid"

    # Forgotten password: staff set a temporary one; the applicant signs in with it.
    accounts = ok(staff.get("/api/admin/accounts?module=visa"))
    temp = ok(staff.post(f"/api/admin/accounts/{accounts[0]['id']}/reset-password"))
    fresh = new_client(api)
    assert signin_applicant(fresh, "visa", temp["username"], PASSWORD).status_code != 200
    assert signin_applicant(fresh, "visa", temp["username"], temp["temporary_password"]).status_code == 200
    assert ok(fresh.get("/api/me/visa/applications"))[0]["status"] == "completed"

    # Audit trail covers the work.
    actions = {r[0] for r in conn.execute(text("SELECT action FROM audit_log"))}
    for action in ("catalog.visa_program_saved", "application.started", "application.stage", "application.status",
                   "application.email", "application.agent_set", "commission.paid", "applicant.password_reset_by_staff"):
        assert action in actions, action


def test_journey_every_module_side_by_side(
    api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    """Training, Student Consultancy, Job Processing and Immigration in one installation."""
    license_modules(conn, *ALL)
    act_as("super_admin")
    group = ok(client.post("/api/admin/course-groups", json=group_body()))
    course = ok(client.post("/api/admin/courses", json=course_body(group["id"])))
    uni = ok(client.post("/api/admin/universities", json=university_body()))
    vac = ok(client.post("/api/admin/vacancies", json=vacancy_body()))
    program = ok(client.post("/api/admin/visa-programs", json=visa_body()))
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")

    # Training: enrol, pay at the office, finance verifies, certificate approved and checked.
    learner = new_client(api)
    verified_applicant(learner, conn, "course", "learner@example.test")
    started = ok(learner.post("/api/me/course/enrolments", json={"course_slug": course["slug"], "method": "manual", "manual_ref": "CASH-1", "phone": "01712345678"}))
    ok(finance.post(f"/api/admin/payments/{started['payment_id']}/verify"))
    enrolment = ok(learner.get("/api/me/course/enrolments"))[0]
    assert enrolment["status"] == "active"
    ok(client.post(f"/api/admin/enrolments/{enrolment['id']}/approve-certificate"))
    assert ok(new_client(api).get(f"/api/certificates/{enrolment['certificate_id']}"))["valid"] is True

    # Student Consultancy: match, apply, pay, upload; the official link opens after paying.
    student = new_client(api)
    verified_applicant(student, conn, "study", "student@example.test")
    assert ok(student.post("/api/match/study", json={"level": "Bachelor", "field": "Computer Science", "gpa": 3.5, "ielts": 7, "budget_usd": 30000}))
    study_app = ok(student.post("/api/me/study/applications", json={"item_slug": uni["slug"], "answers": {"gpa": 3.5}}))
    pay_manual_and_verify(student, finance, "study", study_app["id"], "BANK-STU-1")
    assert ok(student.get(f"/api/me/study/applications/{study_app['id']}"))["apply_link"] == "https://apply.example.test"
    upload(student, "study", study_app["id"], "Valid passport")

    # Job Processing: match, apply, pay, interview and offer.
    worker = new_client(api)
    verified_applicant(worker, conn, "job", "worker@example.test")
    matches = ok(worker.post("/api/match/job", json={"occupation": "Construction", "country": "UAE", "experience": 4, "education": "SSC / HSC", "english": "Basic", "passport_ready": True}))
    assert matches and matches[0]["match_percent"] == 100
    job_app = ok(worker.post("/api/me/job/applications", json={"item_slug": vac["slug"], "answers": {"passport_ready": True}}))
    pay_manual_and_verify(worker, finance, "job", job_app["id"], "BANK-JOB-1")
    ok(client.patch(f"/api/admin/applications/{job_app['id']}", json={"interview_at": "2027-02-01T09:00:00", "interview_result": "passed", "offered_salary_usd": 950}))
    assert ok(worker.get(f"/api/me/job/applications/{job_app['id']}"))["offered_salary_usd"] == 950

    # Immigration: apply and pay.
    traveller = new_client(api)
    verified_applicant(traveller, conn, "visa", "traveller@example.test")
    visa_app = ok(traveller.post("/api/me/visa/applications", json={"item_slug": program["slug"], "answers": {}}))
    pay_manual_and_verify(traveller, finance, "visa", visa_app["id"], "BANK-VIS-1")

    # Sessions are per module: the traveller is not signed in to the other modules.
    assert traveller.get("/api/me/study/applications").status_code == 401

    # Finance: every module's income is in the ledger; nothing is outstanding.
    assert sorted(ledger_categories(conn)) == ["course", "job", "study", "visa"]
    assert ok(finance.get("/api/admin/outstanding"))["items"] == []
    summary = ok(finance.get("/api/admin/ledger/summary"))
    assert summary["balance_all_time_poisha"] == 1_200_000 + 3 * 100000

    # Finance cannot open cases; an admin sees only their sections.
    assert finance.get("/api/admin/applications?module=visa").status_code == 403
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["job"])
    assert staff.get("/api/admin/applications?module=job").status_code == 200
    assert staff.get("/api/admin/applications?module=visa").status_code == 403

    # Licence: without "visa" the module is locked everywhere, the others keep working.
    license_modules(conn, "course", "study", "job")
    assert traveller.get("/api/me/visa/applications").json()["code"] == "MODULE_NOT_LICENSED"
    assert client.get("/api/admin/applications?module=visa").json()["code"] == "MODULE_NOT_LICENSED"
    assert ok(worker.get("/api/me/job/applications"))
