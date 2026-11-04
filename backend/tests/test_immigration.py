"""B19: Immigration Processing (module "visa"): visa programmes, applications, documents,
fees, agents and partners, following the Student Consultancy and Job Processing pattern."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client

ALL = ("course", "study", "job", "visa")


def visa_body(**changes: Any) -> dict[str, Any]:
    return {
        "title": "Visitor Visa",
        "country": "Canada",
        "visa_type": "visit",
        "processing_time": "4 to 8 weeks",
        "validity": "Up to 10 years",
        "government_fee": "CAD 100",
        "description": "Visit family or travel.",
        "eligibility": ["Valid passport", "Enough funds"],
        "required_documents": ["Passport", "Bank statement"],
        "conditions": "",
        "official_link": "https://visa.example.test",
        "embassy_email": "visa-office@example.test",
        "fee_override_poisha": None,
        "published": True,
        **changes,
    }


@pytest.fixture
def setup(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    program = client.post("/api/admin/visa-programs", json=visa_body())
    assert program.status_code == 200, program.text
    verified_applicant(client, conn, "visa", "traveller@example.test")
    return {"program": program.json()}


def apply(client: TestClient, slug: str, answers: dict[str, Any] | None = None) -> Any:
    return client.post("/api/me/visa/applications", json={"item_slug": slug, "answers": answers or {}})


def visa_app(client: TestClient, setup: dict[str, Any]) -> dict[str, Any]:
    response = apply(client, setup["program"]["slug"], {"country": "Canada", "visa_type": "visit", "passport_ready": True})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_program_admin_and_public_views(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    program = setup["program"]
    assert program["slug"].startswith("canada-visitor-visa")
    assert program["visa_type_label"] == "Visit visa"
    assert program["official_link"] == "https://visa.example.test"
    assert program["fee_poisha"] == 100000
    assert audit_count(conn, "catalog.visa_program_saved") == 1

    public = client.get("/api/visa-programs").json()
    assert [p["slug"] for p in public] == [program["slug"]]
    # Staff-only fields never go to the public.
    for key in ("official_link", "embassy_email", "fee_override_poisha", "published"):
        assert key not in public[0]
    assert client.get(f"/api/visa-programs/{program['slug']}").status_code == 200

    hidden = client.put(f"/api/admin/visa-programs/{program['id']}", json=visa_body(published=False))
    assert hidden.status_code == 200
    assert client.get("/api/visa-programs").json() == []
    assert client.get(f"/api/visa-programs/{program['slug']}").status_code == 404


@pytest.mark.parametrize(
    "changes",
    [{"visa_type": "holiday"}, {"title": " "}, {"eligibility": []}, {"required_documents": [" "]},
     {"official_link": "http://x.test"}, {"embassy_email": "nope"}, {"fee_override_poisha": 0}],
)
def test_program_input_checked(client: TestClient, setup: dict[str, Any], changes: dict[str, Any]) -> None:
    response = client.post("/api/admin/visa-programs", json=visa_body(**changes))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"


def test_only_super_admin_changes_programs(api: FastAPI, conn: Connection, setup: dict[str, Any]) -> None:
    other = new_client(api)
    sign_in_admin_on(other, conn, "admin", ["visa"])
    response = other.post("/api/admin/visa-programs", json=visa_body())
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_unlicensed_visa_is_refused(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    license_modules(conn, "course", "study", "job")
    for response in (
        client.get("/api/visa-programs"),
        client.get("/api/admin/visa-programs"),
        client.post("/api/match/visa", json={"country": "Canada", "passport_ready": True}),
        client.get("/api/partners?module=visa"),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "MODULE_NOT_LICENSED"
    assert client.get("/api/catalog/options").json()["visa_countries"] == []


def test_apply_stages_and_case_view(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = visa_app(client, setup)
    assert app["module"] == "visa"
    assert (app["stage"], app["stage_count"], app["stage_name"]) == (0, 8, "Application started")
    assert app["item"]["title"] == "Visitor Visa"
    assert "official_link" not in app["item"]
    assert app["item"]["required_documents"] == ["Passport", "Bank statement"]
    assert "Valid passport (all pages)" in app["required_types"]
    assert visa_app(client, setup)["id"] == app["id"]  # one open application per programme

    mine = client.get("/api/me/visa/applications").json()
    assert [a["item_title"] for a in mine] == ["Visitor Visa"]
    assert mine[0]["item_country"] == "Canada"

    listed = client.get("/api/admin/applications?module=visa").json()
    assert listed["total"] == 1
    case = listed["items"][0]
    assert case["provider_email"] == "visa-office@example.test"
    assert case["item"]["title"] == "Visitor Visa"

    moved = client.post(f"/api/admin/applications/{app['id']}/stage", json={"stage": 7, "note": "", "notify": False})
    assert moved.status_code == 200
    assert (moved.json()["stage_name"], moved.json()["status"]) == ("Ready to travel ✈", "completed")
    emailed = client.post(
        f"/api/admin/applications/{app['id']}/email", json={"to": "provider", "subject": "File", "body": "Hello"}
    )
    assert emailed.status_code == 200
    assert emailed.json()["history"][0]["text"] == "Email sent to embassy: File"


def test_visa_answers_checked(client: TestClient, setup: dict[str, Any]) -> None:
    assert apply(client, setup["program"]["slug"], {"passport_ready": "yes"}).status_code == 422
    assert apply(client, setup["program"]["slug"], {"gpa": 3}).status_code == 422


def test_admin_of_other_section_cannot_see_visa_cases(api: FastAPI, conn: Connection, setup: dict[str, Any]) -> None:
    other = new_client(api)
    sign_in_admin_on(other, conn, "admin", ["study"])
    assert other.get("/api/admin/applications?module=visa").status_code == 403
    visa_admin = new_client(api)
    sign_in_admin_on(visa_admin, conn, "admin", ["visa"])
    assert visa_admin.get("/api/admin/applications?module=visa").status_code == 200


def test_match_and_options(client: TestClient, setup: dict[str, Any]) -> None:
    matches = client.post("/api/match/visa", json={"country": "Canada", "visa_type": "any", "passport_ready": True})
    assert matches.status_code == 200
    assert [m["item"]["slug"] for m in matches.json()] == [setup["program"]["slug"]]
    assert matches.json()[0]["match_percent"] == 100
    assert client.post("/api/match/visa", json={"country": "Japan", "passport_ready": True}).json() == []
    assert client.post("/api/match/visa", json={"country": "Canada", "visa_type": "x", "passport_ready": True}).status_code == 422
    options = client.get("/api/catalog/options").json()
    assert "Canada" in options["visa_countries"]
    assert options["visa_types"] == ["visit"]


def test_fees_and_settings(client: TestClient, setup: dict[str, Any], settings_body: Callable[..., dict[str, Any]]) -> None:
    fees = client.get("/api/admin/fees").json()
    assert fees["defaults"]["visa"] == 100000
    assert [f["name"] for f in fees["visa_programs"]] == ["Visitor Visa"]
    saved = client.put("/api/admin/fees", json={"visa": {setup["program"]["id"]: 250000}})
    assert saved.json()["visa_programs"][0]["effective_poisha"] == 250000
    assert client.get("/api/settings/public").json()["default_fee_poisha"]["visa"] == 100000


def test_visa_account_prefix(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    public_id = conn.execute(
        text("SELECT public_id FROM applicant_accounts WHERE module = 'visa' ORDER BY created_at DESC LIMIT 1")
    ).scalar_one()
    assert public_id.startswith("VIS-")


def test_agents_and_partners_work_in_visa(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    agent = client.post(
        "/api/admin/agents",
        json={
            "name": "Visa Agent",
            "firm": "",
            "phone": "",
            "email": "",
            "country": "",
            "address": "",
            "sections": ["visa"],
            "commission_type": "fixed",
            "commission_poisha": 50000,
            "commission_percent_bp": 0,
            "notes": "",
            "active": True,
        },
    )
    assert agent.status_code == 200, agent.text
    app = visa_app(client, setup)
    linked = client.put(f"/api/admin/applications/{app['id']}/agent", json={"agent_id": agent.json()["id"]})
    assert linked.status_code == 200, linked.text
    commissions = client.get("/api/admin/agents/commissions?module=visa").json()
    assert [(c["module"], c["amount_poisha"]) for c in commissions] == [("visa", 50000)]

    partner = client.post(
        "/api/admin/partners",
        json={
            "module": "visa",
            "partner_type": "visa_centre",
            "name": "Test Visa Centre",
            "country": "Bangladesh",
            "website": "",
            "description": "",
            "contact_name": "",
            "contact_email": "",
            "contact_phone": "",
            "agreement_ref": "",
            "agreement_until": None,
            "show_on_site": True,
            "sort_order": 0,
            "active": True,
        },
    )
    assert partner.status_code == 200, partner.text
    assert [p["name"] for p in client.get("/api/partners?module=visa").json()] == ["Test Visa Centre"]
    assert client.get("/api/partners?module=job").json() == []
