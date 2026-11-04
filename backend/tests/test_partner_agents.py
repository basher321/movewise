"""B16: partner agents, the agent of a case, and commissions (b132-b138)."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import university_body, vacancy_body

ALL = ("course", "study", "job")


def agent_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Test Agent",
        "firm": "Test Partners Ltd",
        "phone": "+8801700000000",
        "email": f"agent-{uuid4().hex[:6]}@example.test",
        "country": "Bangladesh",
        "address": "",
        "sections": ["study", "job"],
        "commission_type": "fixed",
        "commission_poisha": 500000,
        "commission_percent_bp": 0,
        "notes": "",
        "active": True,
    }
    body.update(changes)
    return body


@pytest.fixture
def setup(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    uni = client.post("/api/admin/universities", json=university_body(admissions_email="")).json()
    vac = client.post("/api/admin/vacancies", json=vacancy_body()).json()
    verified_applicant(client, conn, "study", f"student-{uuid4().hex[:6]}@example.test")
    verified_applicant(client, conn, "job", f"worker-{uuid4().hex[:6]}@example.test")
    study = client.post("/api/me/study/applications", json={"item_slug": uni["slug"], "answers": {}}).json()
    job = client.post(
        "/api/me/job/applications", json={"item_slug": vac["slug"], "answers": {"passport_ready": True}}
    ).json()
    return {"uni": uni, "vac": vac, "study": study, "job": job}


def create(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/admin/agents", json=agent_body(**changes))
    assert response.status_code == 200, response.text
    return dict(response.json())


def link(client: TestClient, app_id: str, agent_id: str | None) -> Any:
    return client.put(f"/api/admin/applications/{app_id}/agent", json={"agent_id": agent_id})


def commissions(client: TestClient, **query: str) -> list[dict[str, Any]]:
    response = client.get("/api/admin/agents/commissions", params=query)
    assert response.status_code == 200, response.text
    return list(response.json())


# b132
def test_b132_create_edit_switch_off(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    before = audit_count(conn)
    agent = create(client)
    assert agent["referred"] == 0 and agent["due_poisha"] == 0 and agent["sections"] == ["study", "job"]
    edited = client.put(f"/api/admin/agents/{agent['id']}", json=agent_body(name="Renamed", email=agent["email"]))
    assert edited.status_code == 200 and edited.json()["name"] == "Renamed"
    off = client.put(f"/api/admin/agents/{agent['id']}", json=agent_body(name="Renamed", email=agent["email"], active=False))
    assert off.status_code == 200 and off.json()["active"] is False
    assert audit_count(conn) == before + 3
    assert audit_count(conn, "agent.created") >= 1 and audit_count(conn, "agent.updated") >= 2
    listed = client.get("/api/admin/agents", params={"active": "false"}).json()
    assert [a["id"] for a in listed] == [agent["id"]]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  "},
        {"sections": []},
        {"sections": ["course"]},
        {"commission_type": "other"},
        {"commission_poisha": -1},
        {"commission_percent_bp": 10001},
        {"email": "not an email"},
        {"commission_poisha": 1.5},
        {"active": "yes"},
    ],
)
def test_agent_input_checked(client: TestClient, conn: Connection, setup: dict[str, Any], changes: dict[str, Any]) -> None:
    before = audit_count(conn)
    response = client.post("/api/admin/agents", json=agent_body(**changes))
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION"
    assert audit_count(conn) == before


def test_duplicate_email_conflict(client: TestClient, setup: dict[str, Any]) -> None:
    agent = create(client)
    again = client.post("/api/admin/agents", json=agent_body(email=agent["email"].upper()))
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT"


def test_unknown_agent_404(client: TestClient, setup: dict[str, Any]) -> None:
    assert client.put("/api/admin/agents/not-a-uuid", json=agent_body()).status_code == 404
    assert client.put(f"/api/admin/agents/{uuid4()}", json=agent_body()).json()["code"] == "NOT_FOUND"


# b133
def test_b133_admin_sees_own_sections_only(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    study_agent = create(client, name="Study only", sections=["study"])
    create(client, name="Job only", sections=["job"])
    admin = new_client(api)
    sign_in_admin_on(admin, conn, "admin", ["study"])
    names = [a["name"] for a in admin.get("/api/admin/agents").json()]
    assert names == ["Study only"]
    assert admin.post("/api/admin/agents", json=agent_body()).json()["code"] == "FORBIDDEN"
    assert admin.put(f"/api/admin/agents/{study_agent['id']}", json=agent_body()).json()["code"] == "FORBIDDEN"
    assert admin.get("/api/admin/agents", params={"section": "job"}).json()["code"] == "FORBIDDEN"
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.get("/api/admin/agents").json()["code"] == "FORBIDDEN"
    assert finance.get("/api/admin/agents/commissions").status_code == 200
    course_admin = new_client(api)
    sign_in_admin_on(course_admin, conn, "admin", ["course"])
    assert course_admin.get("/api/admin/agents").json()["code"] == "FORBIDDEN"
    assert course_admin.get("/api/admin/agents/commissions").json()["code"] == "FORBIDDEN"


def test_signed_out_is_401(api: FastAPI, setup: dict[str, Any]) -> None:
    anon = new_client(api)
    anon.cookies.clear()
    for method, path in (
        ("get", "/api/admin/agents"),
        ("post", "/api/admin/agents"),
        ("get", "/api/admin/agents/commissions"),
        ("put", f"/api/admin/applications/{setup['study']['id']}/agent"),
    ):
        response = getattr(anon, method)(path, **({} if method == "get" else {"json": {}}))
        assert response.status_code == 401, (method, path, response.text)


# b134
def test_b134_link_fixed_and_change(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    first = create(client, name="First", commission_poisha=300000)
    second = create(client, name="Second", commission_poisha=700000)
    app_id = setup["study"]["id"]
    case = link(client, app_id, first["id"])
    assert case.status_code == 200, case.text
    assert case.json()["agent"]["name"] == "First"
    rows = commissions(client, agent_id=first["id"])
    assert [(r["status"], r["amount_poisha"]) for r in rows] == [("due", 300000)]
    assert link(client, app_id, second["id"]).json()["agent"]["name"] == "Second"
    assert [r["status"] for r in commissions(client, agent_id=first["id"])] == ["cancelled"]
    assert [(r["status"], r["amount_poisha"]) for r in commissions(client, agent_id=second["id"])] == [("due", 700000)]
    direct = link(client, app_id, None)
    assert direct.json()["agent"] is None
    assert [r["status"] for r in commissions(client, agent_id=second["id"])] == ["cancelled"]
    assert audit_count(conn, "application.agent_set") == 3
    # Linking the same agent twice changes nothing.
    link(client, app_id, first["id"])
    before = audit_count(conn)
    link(client, app_id, first["id"])
    assert audit_count(conn) == before


def test_b134_percent_uses_paid_fee(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = setup["study"]
    applicant_id = conn.execute(text("SELECT applicant_id FROM applications WHERE id = :id"), {"id": app["id"]}).scalar_one()
    conn.execute(
        text(
            "INSERT INTO payments (applicant_id, module, ref_type, ref_id, purpose, amount_poisha, method, status, "
            "tran_id, paid_at) VALUES (:a, 'study', 'application', :r, 'Application fee', 150000, 'manual', 'paid', "
            ":t, now())"
        ),
        {"a": applicant_id, "r": app["id"], "t": "TEST" + uuid4().hex[:12]},
    )
    agent = create(client, commission_type="percent", commission_percent_bp=1250)
    link(client, app["id"], agent["id"])
    assert commissions(client, agent_id=agent["id"])[0]["amount_poisha"] == 18750  # 12.50 % of 1,500 taka
    zero = create(client, commission_type="percent", commission_percent_bp=1000)
    link(client, setup["job"]["id"], zero["id"])
    assert commissions(client, agent_id=zero["id"])[0]["amount_poisha"] == 0  # nothing paid yet


# b135
def test_b135_link_rules(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    job_only = create(client, sections=["job"])
    off = create(client, active=False)
    assert link(client, setup["study"]["id"], job_only["id"]).json()["code"] == "VALIDATION"
    assert link(client, setup["study"]["id"], off["id"]).json()["code"] == "VALIDATION"
    assert link(client, setup["study"]["id"], "nonsense").json()["code"] == "VALIDATION"
    assert link(client, setup["study"]["id"], str(uuid4())).json()["code"] == "VALIDATION"
    assert link(client, str(uuid4()), job_only["id"]).json()["code"] == "NOT_FOUND"
    license_modules(conn, "course", "study")
    response = link(client, setup["job"]["id"], job_only["id"])
    assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"


def test_admin_of_other_section_cannot_link(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    agent = create(client)
    admin = new_client(api)
    sign_in_admin_on(admin, conn, "admin", ["study"])
    assert link(admin, setup["job"]["id"], agent["id"]).json()["code"] == "FORBIDDEN"
    assert link(admin, setup["study"]["id"], agent["id"]).status_code == 200
    assert [c["module"] for c in commissions(admin)] == ["study"]
    assert admin.get("/api/admin/agents/commissions", params={"module": "job"}).json()["code"] == "FORBIDDEN"


# b136
def test_b136_pay_is_final(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    agent = create(client)
    other = create(client, name="Other")
    link(client, setup["study"]["id"], agent["id"])
    row = commissions(client, agent_id=agent["id"])[0]
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.put(f"/api/admin/agents/commissions/{row['id']}", json={"amount_poisha": 1}).json()["code"] == "FORBIDDEN"
    admin = new_client(api)
    sign_in_admin_on(admin, conn, "admin", ["study"])
    assert admin.post(f"/api/admin/agents/commissions/{row['id']}/pay", json={}).json()["code"] == "FORBIDDEN"
    edited = client.put(f"/api/admin/agents/commissions/{row['id']}", json={"amount_poisha": 450000, "note": "agreed"})
    assert edited.status_code == 200 and edited.json()["amount_poisha"] == 450000
    paid = finance.post(f"/api/admin/agents/commissions/{row['id']}/pay", json={"pay_reference": "BANK-42"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid" and paid.json()["paid_at"] and paid.json()["pay_reference"] == "BANK-42"
    for response in (
        client.put(f"/api/admin/agents/commissions/{row['id']}", json={"amount_poisha": 1}),
        client.post(f"/api/admin/agents/commissions/{row['id']}/cancel", json={}),
        finance.post(f"/api/admin/agents/commissions/{row['id']}/pay", json={}),
        link(client, setup["study"]["id"], other["id"]),
        link(client, setup["study"]["id"], None),
    ):
        assert response.status_code == 409 and response.json()["code"] == "CONFLICT", response.text
    assert audit_count(conn, "commission.paid") == 1 and audit_count(conn, "commission.updated") == 1
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("UPDATE agent_commissions SET amount_poisha = 1 WHERE id = :id"), {"id": row["id"]})


def test_cancel_and_bad_input(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    agent = create(client)
    link(client, setup["job"]["id"], agent["id"])
    row = commissions(client, agent_id=agent["id"])[0]
    assert client.put(f"/api/admin/agents/commissions/{row['id']}", json={"amount_poisha": -5}).json()["code"] == "VALIDATION"
    assert client.put(f"/api/admin/agents/commissions/{row['id']}", json={"amount_poisha": "5"}).json()["code"] == "VALIDATION"
    assert client.post(f"/api/admin/agents/commissions/{uuid4()}/pay", json={}).json()["code"] == "NOT_FOUND"
    cancelled = client.post(f"/api/admin/agents/commissions/{row['id']}/cancel", json={"note": "Wrong agent"})
    assert cancelled.json()["status"] == "cancelled" and cancelled.json()["note"] == "Wrong agent"
    assert audit_count(conn, "commission.cancelled") == 1
    assert client.get("/api/admin/agents/commissions", params={"status": "weird"}).json()["code"] == "VALIDATION"


# b137
def test_b137_totals(client: TestClient, setup: dict[str, Any]) -> None:
    agent = create(client, commission_poisha=100000)
    link(client, setup["study"]["id"], agent["id"])
    link(client, setup["job"]["id"], agent["id"])
    rows = commissions(client, agent_id=agent["id"])
    client.post(f"/api/admin/agents/commissions/{rows[0]['id']}/pay", json={})
    listed = {a["id"]: a for a in client.get("/api/admin/agents").json()}[agent["id"]]
    assert listed["referred"] == 2 and listed["due_poisha"] == 100000 and listed["paid_poisha"] == 100000


# b138
def test_b138_no_delete(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    agent = create(client)
    link(client, setup["study"]["id"], agent["id"])
    for sql in ("DELETE FROM agent_commissions WHERE agent_id = :id", "DELETE FROM partner_agents WHERE id = :id"):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql), {"id": agent["id"]})
    for method, path in (("delete", f"/api/admin/agents/{agent['id']}"),):
        assert getattr(client, method)(path).status_code in (404, 405)


def test_case_view_shows_agent(client: TestClient, setup: dict[str, Any]) -> None:
    app_id = setup["study"]["id"]
    assert client.get(f"/api/admin/applications/{app_id}").json()["agent"] is None
    agent = create(client, name="Shown Agent")
    link(client, app_id, agent["id"])
    assert client.get(f"/api/admin/applications/{app_id}").json()["agent"]["name"] == "Shown Agent"
    listed = client.get("/api/admin/applications", params={"module": "study"}).json()
    items = listed["items"] if isinstance(listed, dict) else listed
    assert any(i.get("agent") and i["agent"]["name"] == "Shown Agent" for i in items)
