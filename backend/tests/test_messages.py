"""B20: staff messages to one client or a group, by email, WhatsApp or both (b162-b164)."""

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
from test_immigration import visa_body

ALL = ("course", "study", "job", "visa")


@pytest.fixture
def world(api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    canada = client.post("/api/admin/visa-programs", json=visa_body()).json()
    uk = client.post("/api/admin/visa-programs", json=visa_body(title="Spouse Visa", country="UK", visa_type="spouse")).json()
    people = []
    for i, (email, phone, program) in enumerate(
        [("a@example.test", "01711111111", canada), ("b@example.test", "", canada), (None, "01733333333", uk), ("d@example.test", "", None)]
    ):
        person = new_client(api)
        verified_applicant(person, conn, "visa", f"person{i}@example.test")
        conn.execute(
            text("UPDATE applicant_accounts SET email = :e, phone = :p WHERE module = 'visa' AND email = :signup"),
            {"e": email, "p": phone, "signup": f"person{i}@example.test"},
        )
        if program:
            person.post("/api/me/visa/applications", json={"item_slug": program["slug"], "answers": {}})
        people.append(person)
    conn.execute(text("UPDATE notifications SET status = 'sent' WHERE status = 'queued'"))
    accounts = client.get("/api/admin/accounts?module=visa").json()
    return {"canada": canada, "uk": uk, "accounts": accounts}


def staff_rows(conn: Connection) -> list[Any]:
    return list(conn.execute(text("SELECT channel, to_address, sent_by, batch_id FROM notifications WHERE event = 'staff_message'")).mappings())


def msg(**changes: Any) -> dict[str, Any]:
    return {"channels": ["email", "whatsapp"], "subject": "Embassy update", "body": "Your appointment is confirmed.", **changes}


# b162
def test_b162_one_client(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    by_email = {a["email"]: a for a in world["accounts"]}
    both = by_email["a@example.test"]["id"]
    assert client.post("/api/admin/messages", json=msg(account_id=both)).json() == {"queued": 2}
    assert client.post("/api/admin/messages", json=msg(account_id=both, channels=["whatsapp"])).json() == {"queued": 1}
    email_only = by_email["b@example.test"]["id"]
    assert client.post("/api/admin/messages", json=msg(account_id=email_only, channels=["whatsapp"])).status_code == 422
    rows = staff_rows(conn)
    assert len(rows) == 3 and all(r["sent_by"] is not None and r["batch_id"] is None for r in rows)
    assert audit_count(conn, "message.sent") == 2
    for bad in ({"subject": " "}, {"body": ""}, {"channels": []}, {"channels": ["sms"]}, {"subject": "x" * 201}):
        assert client.post("/api/admin/messages", json=msg(account_id=both, **bad)).status_code == 422, bad
    assert client.post("/api/admin/messages", json=msg(account_id="not-a-uuid")).status_code == 404

    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.post("/api/admin/messages", json=msg(account_id=both)).status_code == 403
    other = new_client(api)
    sign_in_admin_on(other, conn, "admin", ["study"])
    assert other.post("/api/admin/messages", json=msg(account_id=both)).status_code == 403
    visa_staff = new_client(api)
    sign_in_admin_on(visa_staff, conn, "admin", ["visa"])
    assert visa_staff.post("/api/admin/messages", json=msg(account_id=both, channels=["email"])).json() == {"queued": 1}

    license_modules(conn, "course", "study", "job")
    assert client.post("/api/admin/messages", json=msg(account_id=both)).json()["code"] == "MODULE_NOT_LICENSED"


# b163
def test_b163_group(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    def preview(filters: dict[str, Any]) -> dict[str, int]:
        response = client.post("/api/admin/messages/bulk/preview", json={"module": "visa", "filters": filters})
        assert response.status_code == 200, response.text
        return dict(response.json())

    assert preview({}) == {"recipients": 4, "with_email": 3, "with_whatsapp": 2}
    assert preview({"item_id": world["canada"]["id"]})["recipients"] == 2
    assert preview({"has_application": False})["recipients"] == 1
    assert preview({"status": "active", "stage": 0})["recipients"] == 3
    assert preview({"stage": 3})["recipients"] == 0
    assert client.post("/api/admin/messages/bulk/preview", json={"module": "visa", "filters": {"status": "x"}}).status_code == 422
    assert client.post("/api/admin/messages/bulk/preview", json={"module": "visa", "filters": {"enrolment_status": "active"}}).status_code == 422

    body = {**msg(), "module": "visa", "filters": {"item_id": world["canada"]["id"]}, "expected_recipients": 3}
    assert client.post("/api/admin/messages/bulk", json=body).status_code == 409
    sent = client.post("/api/admin/messages/bulk", json={**body, "expected_recipients": 2}).json()
    # a@ gets email + WhatsApp, b@ email only.
    assert sent["queued"] == 3
    rows = staff_rows(conn)
    assert {r["to_address"] for r in rows} == {"a@example.test", "b@example.test", "01711111111"}
    assert all(str(r["batch_id"]) == sent["batch_id"] for r in rows)
    batch = conn.execute(text("SELECT recipients, channels, module FROM message_batches")).one()
    assert (batch[0], list(batch[1]), batch[2]) == (2, ["email", "whatsapp"], "visa")
    assert audit_count(conn, "message.bulk_sent") == 1
    none = {**msg(), "module": "visa", "filters": {"stage": 5}, "expected_recipients": 0}
    assert client.post("/api/admin/messages/bulk", json=none).status_code == 422


def test_group_for_training(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    learner = new_client(api)
    verified_applicant(learner, conn, "course", "learner@example.test")
    conn.execute(text("UPDATE applicant_accounts SET email = 'learner@example.test' WHERE module = 'course'"))
    counts = client.post("/api/admin/messages/bulk/preview", json={"module": "course", "filters": {"has_application": False}}).json()
    assert counts["recipients"] == 1
    assert client.post("/api/admin/messages/bulk/preview", json={"module": "course", "filters": {"stage": 1}}).status_code == 422


def test_group_limit(client: TestClient, conn: Connection, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import messages

    monkeypatch.setattr(messages, "MAX_RECIPIENTS", 3)
    body = {**msg(), "module": "visa", "filters": {}, "expected_recipients": 4}
    response = client.post("/api/admin/messages/bulk", json=body)
    assert response.status_code == 422 and "At most 3" in response.json()["message"]


# b164
def test_b164_batches_cannot_change(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    body = {**msg(), "module": "visa", "filters": {}, "expected_recipients": 4}
    client.post("/api/admin/messages/bulk", json=body)
    for sql in ("UPDATE message_batches SET subject = 'x'", "DELETE FROM message_batches WHERE recipients = 4"):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql))


def test_case_message_channels(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app_id = conn.execute(
        text("SELECT a.id FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id WHERE p.email = 'a@example.test'")
    ).scalar_one()
    body = {"to": "applicant", "subject": "Hello", "body": "Update", "channels": ["whatsapp"]}
    assert client.post(f"/api/admin/applications/{app_id}/email", json=body).status_code == 200
    rows = conn.execute(text("SELECT channel FROM notifications WHERE event = 'case_email'")).scalars().all()
    assert rows == ["whatsapp"]
    # Default stays both channels, as before B20.
    client.post(f"/api/admin/applications/{app_id}/email", json={"to": "applicant", "subject": "Hi", "body": "Again"})
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'case_email'")).scalar_one() == 3
    email_only = conn.execute(
        text("SELECT a.id FROM applications a JOIN applicant_accounts p ON p.id = a.applicant_id WHERE p.email = 'b@example.test'")
    ).scalar_one()
    assert client.post(f"/api/admin/applications/{email_only}/email", json=body).status_code == 422
