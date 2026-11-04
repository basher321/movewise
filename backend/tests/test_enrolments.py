"""B09: course enrolments, certificates, enquiries and the audit list (b97-b108)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.crypto import encrypt
from app.licence import today_dhaka
from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import course_body, group_body
from test_payments import SECRETS, FakeGateway, fake  # noqa: F401  (fake is a fixture)

PRICE = 1_200_000


@pytest.fixture
def course_world(client: TestClient, conn: Connection, act_as: Callable[..., Any], fake: FakeGateway) -> dict[str, Any]:  # noqa: F811
    license_modules(conn, "course", "study", "job")
    conn.execute(
        text("UPDATE settings SET sslcommerz_enabled = true, bkash_enabled = true, manual_enabled = true, "
             "email = 'office@agency.test' WHERE singleton = 'settings'")
    )
    for name, value in SECRETS.items():
        conn.execute(text("INSERT INTO settings_secrets (name, ciphertext) VALUES (:n, :c)"), {"n": name, "c": encrypt(name, value)})
    act_as("super_admin")
    group = client.post("/api/admin/course-groups", json=group_body()).json()
    course = client.post("/api/admin/courses", json=course_body(group["id"])).json()
    verified_applicant(client, conn, "course", "learner@example.test")
    return {"course": course, "group": group}


def enrol(client: TestClient, slug: str, method: str = "bkash", **extra: Any) -> Any:
    return client.post("/api/me/course/enrolments", json={"course_slug": slug, "method": method, "phone": "01712345678", **extra})


def pay_by_bkash(client: TestClient, conn: Connection, fake: FakeGateway, slug: str) -> dict[str, Any]:  # noqa: F811
    started = enrol(client, slug).json()
    payment = conn.execute(text("SELECT * FROM payments WHERE id = :id"), {"id": started["payment_id"]}).mappings().one()
    fake.execute = {"transactionStatus": "Completed", "amount": f"{payment['amount_poisha'] // 100}.00",
                    "merchantInvoiceNumber": payment["tran_id"], "trxID": "TRX-C1"}
    client.get(f"/api/pay/bkash/callback?paymentID={payment['gateway_session']}&status=success", follow_redirects=False)
    return dict(client.get("/api/me/course/enrolments").json()[0])


# b97
@pytest.mark.parametrize(
    "sql",
    ["DELETE FROM enrolments WHERE true", "DELETE FROM enquiries WHERE true", "UPDATE enquiry_notes SET text = 'x' WHERE true",
     "DELETE FROM enquiry_notes WHERE true"],
)
def test_b97_blocked(client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway, sql: str) -> None:  # noqa: F811
    pay_by_bkash(client, conn, fake, course_world["course"]["slug"])
    added = client.post("/api/admin/enquiries", json={"name": "A", "contact": "a@example.test", "interest": "course"}).json()
    client.post(f"/api/admin/enquiries/{added['id']}/notes", json={"text": "Called"})
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text(sql))


# b98
def test_b98_enrol_and_pay(client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway) -> None:  # noqa: F811
    slug = course_world["course"]["slug"]
    enrolment = pay_by_bkash(client, conn, fake, slug)
    assert enrolment["status"] == "active" and enrolment["certificate_id"].startswith("CERT-")
    assert enrolment["payment_status"] == "paid" and enrolment["price_poisha"] == PRICE
    assert conn.execute(text("SELECT count(*) FROM invoices WHERE module = 'course'")).scalar_one() == 1
    assert conn.execute(text("SELECT category FROM ledger_entries")).scalar_one() == "course"
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'enrolled'")).scalar_one() == 1
    again = enrol(client, slug)
    assert again.status_code == 409 and again.json()["message"] == "You already have this course."


# b99
def test_b99_manual(api: FastAPI, client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    slug = course_world["course"]["slug"]
    started = enrol(client, slug, method="manual", manual_ref="CASH-77").json()
    assert started["status"] == "pending_verify" and started["enrolment"]["status"] == "awaiting_payment"
    mine = client.get("/api/me/course/enrolments").json()[0]
    assert (mine["status"], mine["payment_status"], mine["certificate_id"]) == ("awaiting_payment", "pending_verify", None)
    waiting = enrol(client, slug, method="manual", manual_ref="CASH-78")
    assert waiting.status_code == 409 and "waiting for verification" in waiting.json()["message"]
    outstanding = client.get("/api/admin/outstanding").json()["items"]
    assert any(i["ref_type"] == "enrolment" and i["status"] == "pending_verify" for i in outstanding)
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.post(f"/api/admin/payments/{started['payment_id']}/verify").json()["status"] == "paid"
    assert client.get("/api/me/course/enrolments").json()[0]["status"] == "active"


def test_unpaid_enrolment_is_reused(client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    slug = course_world["course"]["slug"]
    first = enrol(client, slug).json()
    second = enrol(client, slug).json()
    assert first["enrolment"]["order_no"] == second["enrolment"]["order_no"]
    assert conn.execute(text("SELECT count(*) FROM enrolments")).scalar_one() == 1


# b100
def test_b100_price_locked(client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway) -> None:  # noqa: F811
    course = course_world["course"]
    started = enrol(client, course["slug"]).json()
    client.put(f"/api/admin/courses/{course['id']}", json=course_body(course["group_id"], price_poisha=2_000_000))
    again = enrol(client, course["slug"]).json()
    assert again["enrolment"]["price_poisha"] == PRICE
    amount = conn.execute(text("SELECT amount_poisha FROM payments WHERE id = :id"), {"id": again["payment_id"]}).scalar_one()
    assert amount == PRICE and started["enrolment"]["price_poisha"] == PRICE


# b101
def test_b101_certificate_check(api: FastAPI, client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway) -> None:  # noqa: F811
    enrolment = pay_by_bkash(client, conn, fake, course_world["course"]["slug"])
    cert = enrolment["certificate_id"]
    public = new_client(api)
    assert public.get(f"/api/certificates/{cert}").status_code == 404
    admin_id = enrolment["id"]
    approved = client.post(f"/api/admin/enrolments/{admin_id}/approve-certificate")
    assert approved.json()["status"] == "completed"
    answer = public.get(f"/api/certificates/{cert.lower()}").json()
    assert set(answer) == {"valid", "name", "course_title", "duration", "level", "issued_at"}
    assert answer["valid"] is True and answer["name"] == "Test Person"
    no = conn.execute(text("SELECT no FROM invoices")).scalar_one()
    refund = client.post("/api/me/course/refunds", json={"invoice_no": no, "reason": "Could not attend"}).json()
    client.post(f"/api/admin/refunds/{refund['id']}/approve", json={"refund_method": "bKash", "refund_ref": "R1"})
    assert public.get(f"/api/certificates/{cert}").status_code == 404
    assert client.get("/api/me/course/enrolments").json()[0]["status"] == "cancelled"


# b102
def test_b102_certificate_rate_limit(client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    for _ in range(60):
        assert client.get("/api/certificates/CERT-AAAAAAAA").status_code == 404
    response = client.get("/api/certificates/CERT-AAAAAAAA")
    assert response.status_code == 429 and response.json()["code"] == "TOO_MANY_TRIES"


# b103
def test_b103_approve_rules(api: FastAPI, client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    started = enrol(client, course_world["course"]["slug"], method="manual", manual_ref="X1").json()
    eid = started["enrolment"]["id"]
    assert client.post(f"/api/admin/enrolments/{eid}/approve-certificate").status_code == 409
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    assert staff.post(f"/api/admin/enrolments/{eid}/approve-certificate").json()["code"] == "FORBIDDEN"
    assert staff.get("/api/admin/enrolments").json()["code"] == "FORBIDDEN"
    listed = client.get("/api/admin/enrolments?q=learner").json()
    assert listed["total"] == 1 and listed["items"][0]["learner"]["email"] == "learner@example.test"


def enquiry(**changes: Any) -> dict[str, Any]:
    return {"name": "Nadia", "contact": "01712345678", "interest": "study", "message": "Canada for MSc?", **changes}


# b104
def test_b104_enquiry_protection(api: FastAPI, conn: Connection, course_world: dict[str, Any]) -> None:
    public = new_client(api)
    assert public.post("/api/enquiries", json=enquiry(website="http://spam.test")).json() == {"ok": True}
    assert conn.execute(text("SELECT count(*) FROM enquiries")).scalar_one() == 0
    public.post("/api/enquiries", json=enquiry())
    public.post("/api/enquiries", json=enquiry())
    assert conn.execute(text("SELECT count(*) FROM enquiries")).scalar_one() == 1
    for i in range(4):
        assert public.post("/api/enquiries", json=enquiry(message=f"Question {i}")).status_code == 200
    sixth = public.post("/api/enquiries", json=enquiry(message="One more"))
    assert sixth.status_code == 429 and sixth.json()["code"] == "TOO_MANY_TRIES"


def test_enquiry_validation(api: FastAPI, conn: Connection, course_world: dict[str, Any]) -> None:
    public = new_client(api)
    yesterday = (today_dhaka() - timedelta(days=1)).isoformat()
    for bad in ({"name": " "}, {"contact": "hello"}, {"interest": "visa"}, {"message": "x" * 2001}, {"preferred_date": yesterday}):
        assert public.post("/api/enquiries", json=enquiry(**bad)).status_code == 422, bad
    license_modules(conn, "study")
    assert public.post("/api/enquiries", json=enquiry(interest="course")).status_code == 422


# b105
def test_b105_enquiry_email_and_finance(api: FastAPI, conn: Connection, course_world: dict[str, Any]) -> None:
    new_client(api).post("/api/enquiries", json=enquiry())
    note = conn.execute(text("SELECT to_address, subject FROM notifications WHERE event = 'new_enquiry'")).one()
    assert tuple(note) == ("office@agency.test", "New enquiry from Nadia")
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    for method, path in (("get", "/api/admin/enquiries"), ("post", "/api/admin/enquiries")):
        assert finance.request(method, path, json=enquiry()).json()["code"] == "FORBIDDEN"


# b106
def test_b106_notes_and_assign(client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    from conftest import insert_admin

    added = client.post("/api/admin/enquiries", json=enquiry()).json()
    finance_id, _ = insert_admin(conn, "finance")
    assert client.patch(f"/api/admin/enquiries/{added['id']}", json={"assigned_to": str(finance_id)}).status_code == 422
    admin_id, _ = insert_admin(conn, "admin", name="Sumi")
    done = client.patch(f"/api/admin/enquiries/{added['id']}", json={"assigned_to": str(admin_id), "status": "contacted"}).json()
    assert done["assigned_to"]["name"] == "Sumi" and done["status"] == "contacted"
    noted = client.post(f"/api/admin/enquiries/{added['id']}/notes", json={"text": "Called, will visit Sunday"}).json()
    assert noted["notes"][0]["text"] == "Called, will visit Sunday"
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("UPDATE enquiry_notes SET text = 'changed' WHERE true"))


# b107
def test_b107_audit_list(api: FastAPI, client: TestClient, conn: Connection, course_world: dict[str, Any]) -> None:
    for i in range(55):
        client.post("/api/admin/enquiries", json=enquiry(name=f"Person {i}"))
    first = client.get("/api/admin/audit").json()
    assert len(first["rows"]) == 50 and first["total"] >= 55
    assert first["rows"][0]["at"] >= first["rows"][-1]["at"]
    assert len(client.get("/api/admin/audit?page=2").json()["rows"]) == first["total"] - 50
    assert client.get("/api/admin/audit?q=Person 54").json()["total"] == 1
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin")
    assert staff.get("/api/admin/audit").json()["code"] == "FORBIDDEN"
    for route in api.routes:
        if "audit" in getattr(route, "path", ""):
            assert getattr(route, "methods", set()) <= {"GET", "HEAD"}, route


# b108
def test_b108_one_audit_row_per_change(api: FastAPI, client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway) -> None:  # noqa: F811
    def changes(call: Callable[[], Any]) -> Any:
        before = audit_count(conn)
        result = call()
        assert audit_count(conn) == before + 1
        return result

    started = changes(lambda: enrol(client, course_world["course"]["slug"], method="manual", manual_ref="M1").json())
    changes(lambda: client.post(f"/api/admin/payments/{started['payment_id']}/verify"))
    changes(lambda: client.post(f"/api/admin/enrolments/{started['enrolment']['id']}/approve-certificate"))
    changes(lambda: new_client(api).post("/api/enquiries", json=enquiry()))
    added = changes(lambda: client.post("/api/admin/enquiries", json=enquiry(name="Walk-in")).json())
    changes(lambda: client.patch(f"/api/admin/enquiries/{added['id']}", json={"status": "converted"}))
    changes(lambda: client.post(f"/api/admin/enquiries/{added['id']}/notes", json={"text": "Paid"}))
