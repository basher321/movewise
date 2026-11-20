"""B27: custom payments of any amount on a case or course enrolment (b281-b288)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_enrolments import course_world, enrol  # noqa: F401  (course_world is a fixture)
from test_immigration import visa_app, visa_body
from test_payments import FakeGateway, fake, new_app, payment_row, ssl_callback, valid, world  # noqa: F401

AMOUNT = 2_500_000  # 25,000 taka


def ask(client: TestClient, module: str, case_id: str, amount: int = AMOUNT, description: str = "Visa processing fee") -> Any:
    return client.post(
        "/api/admin/payment-requests",
        json={"module": module, "case_id": case_id, "description": description, "amount_poisha": amount},
    )


def pay_request(client: TestClient, module: str, request_id: str, method: str = "manual") -> Any:
    body = {"method": method, "phone": "01712345678", "manual_ref": "BANK-REF-1" if method == "manual" else ""}
    return client.post(f"/api/me/{module}/payment-requests/{request_id}/pay", json=body)


def own(client: TestClient, module: str, case_id: str, amount: int, method: str = "manual", note: str = "Deposit") -> Any:
    return client.post(
        f"/api/me/{module}/own-payments",
        json={"case_id": case_id, "amount_poisha": amount, "note": note, "method": method, "phone": "01712345678",
              "manual_ref": "BANK-REF-2" if method == "manual" else ""},
    )


def request_row(conn: Connection, request_id: str) -> Any:
    return conn.execute(text("SELECT * FROM payment_requests WHERE id = :id"), {"id": request_id}).mappings().one()


# b281
def test_b281_table_rules(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    created = ask(client, "study", app["id"])
    assert created.status_code == 200, created.text
    row = request_row(conn, created.json()["id"])
    enrolment_less = conn.execute(text("SELECT id FROM enrolments LIMIT 1")).scalar_one_or_none()
    for sql, params in (
        ("UPDATE payment_requests SET application_id = NULL WHERE id = :id", {"id": row["id"]}),
        ("UPDATE payment_requests SET enrolment_id = :e WHERE id = :id", {"id": row["id"], "e": enrolment_less or row["id"]}),
        ("UPDATE payment_requests SET amount_poisha = 0 WHERE id = :id", {"id": row["id"]}),
        ("UPDATE payment_requests SET status = 'gone' WHERE id = :id", {"id": row["id"]}),
    ):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql), params)
    started = pay_request(client, "study", created.json()["id"])
    assert started.status_code == 200 and payment_row(conn, started.json()["payment_id"])["ref_type"] == "request"


# b282
def test_b282_staff_request_paid_by_manual(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    created = ask(client, "study", app["id"]).json()
    assert created["status"] == "open" and created["kind"] == "requested" and created["case_ref"] == app["ref"]
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'payment_requested'")).scalar_one() >= 1
    assert audit_count(conn, "payment_request.created") == 1
    mine = client.get("/api/me/study/payment-requests").json()["items"]
    assert [r["ref"] for r in mine] == [created["ref"]]
    started = pay_request(client, "study", created["id"])
    assert started.status_code == 200 and started.json()["status"] == "pending_verify"
    again = pay_request(client, "study", created["id"])
    assert again.status_code == 409
    verified = client.post(f"/api/admin/payments/{started.json()['payment_id']}/verify")
    assert verified.status_code == 200, verified.text
    paid = client.get("/api/me/study/payment-requests").json()["items"][0]
    assert paid["status"] == "paid" and paid["invoice_no"] and paid["payment"]["status"] == "paid"
    ledger = conn.execute(text("SELECT category, amount_poisha FROM ledger_entries")).mappings().one()
    assert ledger["category"] == "study" and ledger["amount_poisha"] == AMOUNT
    assert conn.execute(text("SELECT fee_paid FROM applications WHERE id = :id"), {"id": app["id"]}).scalar_one() is False
    assert pay_request(client, "study", created["id"]).status_code == 409
    # The normal fee is still payable on its own.
    normal = client.post(f"/api/me/study/applications/{app['id']}/pay", json={"method": "manual", "phone": "01712345678", "manual_ref": "R"})
    assert normal.status_code == 200


# b283
def test_b283_course_request_paid_online(client: TestClient, conn: Connection, course_world: dict[str, Any], fake: FakeGateway) -> None:  # noqa: F811
    started = enrol(client, course_world["course"]["slug"], method="manual", manual_ref="R1").json()
    enrolment_id = started["enrolment"]["id"]
    created = ask(client, "course", enrolment_id, description="Exam fee")
    assert created.status_code == 200, created.text
    begun = pay_request(client, "course", created.json()["id"], method="sslcommerz")
    assert begun.status_code == 200 and begun.json()["redirect_url"]
    payment = payment_row(conn, begun.json()["payment_id"])
    fake.validation = valid(payment)
    ssl_callback(client, "success", payment)
    assert request_row(conn, created.json()["id"])["status"] == "paid"
    assert conn.execute(text("SELECT category FROM ledger_entries")).scalar_one() == "course"
    status = conn.execute(text("SELECT status FROM enrolments WHERE id = :id"), {"id": enrolment_id}).scalar_one()
    assert status == "awaiting_payment"


# b284
def test_b284_own_amount_on_a_visa_case(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> None:
    license_modules(conn, "course", "study", "job", "visa", "remote")
    conn.execute(text("UPDATE settings SET manual_enabled = true WHERE singleton = 'settings'"))
    act_as("super_admin")
    program = client.post("/api/admin/visa-programs", json=visa_body()).json()
    verified_applicant(client, conn, "visa", "own@example.test")
    app = visa_app(client, {"program": program})
    for amount in (9_900, 10_050, 100_000_100):
        response = own(client, "visa", app["id"], amount)
        assert response.status_code == 422, response.text
    paid = own(client, "visa", app["id"], 1_000_000)
    assert paid.status_code == 200 and paid.json()["status"] == "pending_verify"
    row = conn.execute(text("SELECT * FROM payment_requests")).mappings().one()
    assert row["kind"] == "own" and row["description"] == "Deposit" and row["created_by_kind"] == "applicant"
    client.post(f"/api/admin/payments/{paid.json()['payment_id']}/verify")
    assert request_row(conn, row["id"])["status"] == "paid"
    # A second own payment on the same case is allowed (any number).
    assert own(client, "visa", app["id"], 500_000, note="").status_code == 200
    assert conn.execute(text("SELECT count(*) FROM payment_requests")).scalar_one() == 2
    # Someone else's case.
    stranger = client.post("/api/auth/applicant/visa/signup", json={"name": "S", "username": "stranger_v", "password": "longenough123"})
    assert stranger.status_code == 200
    assert own(client, "visa", app["id"], 500_000).status_code == 404


def test_rejected_own_amount_is_closed(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    started = own(client, "study", app["id"], 300_000).json()
    rejected = client.post(f"/api/admin/payments/{started['payment_id']}/reject", json={"reason": "No money arrived"})
    assert rejected.status_code == 200
    assert conn.execute(text("SELECT status FROM payment_requests")).scalar_one() == "cancelled"
    # A staff request stays open after a rejected payment.
    created = ask(client, "study", app["id"]).json()
    begun = pay_request(client, "study", created["id"]).json()
    client.post(f"/api/admin/payments/{begun['payment_id']}/reject", json={"reason": "Wrong ref"})
    assert request_row(conn, created["id"])["status"] == "open"
    assert pay_request(client, "study", created["id"]).status_code == 200


# b285
def test_b285_cancel(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    first = ask(client, "study", app["id"]).json()
    cancelled = client.post(f"/api/admin/payment-requests/{first['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert audit_count(conn, "payment_request.cancelled") == 1
    assert pay_request(client, "study", first["id"]).status_code == 409
    assert client.post(f"/api/admin/payment-requests/{first['id']}/cancel").status_code == 409
    second = ask(client, "study", app["id"]).json()
    pay_request(client, "study", second["id"])
    blocked = client.post(f"/api/admin/payment-requests/{second['id']}/cancel")
    assert blocked.status_code == 409


# b286
def test_b286_order_of_checks(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    anonymous = new_client(api)
    anonymous.cookies.clear()
    assert anonymous.post("/api/admin/payment-requests", json={}).status_code == 401
    assert anonymous.get("/api/me/study/payment-requests").status_code == 401
    other = new_client(api)
    sign_in_admin_on(other, conn, "admin", ["job"])
    assert ask(other, "study", app["id"]).status_code == 403
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert ask(finance, "study", app["id"]).status_code == 403
    section = new_client(api)
    sign_in_admin_on(section, conn, "admin", ["study"])
    assert ask(section, "study", app["id"]).status_code == 200
    assert ask(client, "study", app["id"], amount=1_000_050).status_code == 422
    assert ask(client, "study", app["id"], description="  ").status_code == 422
    assert ask(client, "job", app["id"]).status_code == 404
    license_modules(conn, "course", "job")
    assert ask(client, "study", app["id"]).status_code == 403
    assert ask(client, "study", app["id"]).json()["code"] == "MODULE_NOT_LICENSED"


# b287
def test_b287_many_requests_each_with_its_own_invoice(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    for n in range(3):
        created = ask(client, "study", app["id"], amount=100_000 * (n + 1), description=f"Charge {n + 1}").json()
        started = pay_request(client, "study", created["id"]).json()
        client.post(f"/api/admin/payments/{started['payment_id']}/verify")
    items = client.get(f"/api/admin/payment-requests?module=study&case_id={app['id']}").json()["items"]
    assert len(items) == 3 and all(i["status"] == "paid" for i in items)
    assert len({i["invoice_no"] for i in items}) == 3
    assert conn.execute(text("SELECT count(*) FROM ledger_entries")).scalar_one() == 3
