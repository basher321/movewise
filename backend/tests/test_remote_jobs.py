"""Remote Jobs (module "remote"): remote roles, matching, applications, stages, fees, letters,
following the Job Processing pattern without visa, medical or flight steps."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import vacancy_body

ALL = ("course", "study", "job", "visa", "remote")


def remote_body(**changes: Any) -> dict[str, Any]:
    base = {
        "title": "Frontend Developer",
        "employer": "Test Remote Ltd",
        "country": "UK",
        "occupation": "Software development",
        "min_experience": 2,
        "salary_usd": 1500,
        "contract": "Full-time, 1 year",
        "benefits": "Paid leave",
    }
    return vacancy_body(**{**base, **changes})


def remote_input(**changes: Any) -> dict[str, Any]:
    return {
        "occupation": "Software development",
        "country": "Any country",
        "experience": 3,
        "education": "Bachelor or higher",
        "english": "Good",
        "salary_goal_usd": None,
        **changes,
    }


@pytest.fixture
def setup(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    job = client.post("/api/admin/remote-jobs", json=remote_body())
    assert job.status_code == 200, job.text
    onsite = client.post("/api/admin/vacancies", json=vacancy_body())
    assert onsite.status_code == 200, onsite.text
    verified_applicant(client, conn, "remote", "remote.worker@example.test")
    return {"job": job.json(), "onsite": onsite.json()}


def apply(client: TestClient, slug: str, answers: dict[str, Any] | None = None) -> Any:
    return client.post("/api/me/remote/applications", json={"item_slug": slug, "answers": answers or {}})


def test_remote_jobs_are_their_own_section(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    job, onsite = setup["job"], setup["onsite"]
    assert audit_count(conn, "catalog.remote_job_saved") == 1
    assert [j["id"] for j in client.get("/api/admin/remote-jobs").json()] == [job["id"]]
    assert [v["id"] for v in client.get("/api/admin/vacancies").json()] == [onsite["id"]]

    assert [j["slug"] for j in client.get("/api/remote-jobs").json()] == [job["slug"]]
    assert [v["slug"] for v in client.get("/api/vacancies").json()] == [onsite["slug"]]
    assert client.get(f"/api/remote-jobs/{job['slug']}").json()["remote"] is True
    assert client.get(f"/api/remote-jobs/{onsite['slug']}").status_code == 404
    assert client.get(f"/api/vacancies/{job['slug']}").status_code == 404
    # A role stays in the section it was added in.
    assert client.put(f"/api/admin/vacancies/{job['id']}", json=vacancy_body()).status_code == 404
    assert client.put(f"/api/admin/remote-jobs/{onsite['id']}", json=remote_body()).status_code == 404
    saved = client.put(f"/api/admin/remote-jobs/{job['id']}", json=remote_body(salary_usd=1800))
    assert saved.status_code == 200 and saved.json()["salary_usd"] == 1800


def test_only_super_admin_changes_remote_jobs(api: FastAPI, conn: Connection, setup: dict[str, Any]) -> None:
    other = new_client(api)
    sign_in_admin_on(other, conn, "admin", ["remote"])
    response = other.post("/api/admin/remote-jobs", json=remote_body())
    assert response.status_code == 403


def test_unlicensed_remote_is_refused(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    license_modules(conn, "course", "study", "job", "visa")
    for response in (
        client.get("/api/remote-jobs"),
        client.get("/api/admin/remote-jobs"),
        client.post("/api/match/remote", json=remote_input()),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "MODULE_NOT_LICENSED"
    assert client.get("/api/catalog/options").json()["remote_occupations"] == []


def test_match_needs_no_passport(client: TestClient, setup: dict[str, Any]) -> None:
    matches = client.post("/api/match/remote", json=remote_input()).json()
    assert [m["item"]["slug"] for m in matches] == [setup["job"]["slug"]]
    assert matches[0]["match_percent"] == 100
    assert "Passport" not in " ".join(c["label"] for c in matches[0]["checks"])
    assert client.post("/api/match/remote", json=remote_input(country="Japan")).json() == []
    # B25: a role with a different skill still shows when other criteria fit, with a lower match.
    other = client.post("/api/match/remote", json=remote_input(occupation="Construction")).json()
    assert [m["item"]["slug"] for m in other] == [setup["job"]["slug"]]
    assert other[0]["checks"][0] == {"ok": False, "label": "Different skill (Software development)"}
    assert other[0]["match_percent"] == 86
    assert client.post("/api/match/remote", json=remote_input(english="Native")).status_code == 422
    options = client.get("/api/catalog/options").json()
    # Common remote skills are always offered; a role's own skill is added once.
    assert options["remote_occupations"][:2] == ["Software development", "Web development"]
    assert options["remote_occupations"].count("Software development") == 1
    assert options["remote_countries"][0] == "Any country"
    assert {"UK", "Bangladesh", "USA"} <= set(options["remote_countries"])


def test_apply_stages_letter_and_account(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = apply(client, setup["job"]["slug"], {"occupation": "Software development", "experience": 3})
    assert app.status_code == 200, app.text
    app = app.json()
    assert app["module"] == "remote"
    assert (app["stage"], app["stage_count"], app["stage_name"]) == (0, 6, "Application started")
    assert "Portfolio or work samples" in app["required_types"]
    assert all("Medical" not in s and "visa" not in s.lower() for s in app["stages"])
    assert apply(client, setup["onsite"]["slug"]).status_code == 404
    assert apply(client, setup["job"]["slug"], {"passport_ready": True}).status_code == 422

    public_id = conn.execute(
        text("SELECT public_id FROM applicant_accounts WHERE module = 'remote' ORDER BY created_at DESC LIMIT 1")
    ).scalar_one()
    assert public_id.startswith("RMT-")

    case = client.get("/api/admin/applications?module=remote").json()["items"][0]
    assert case["provider_email"] == "hr@example.test"
    moved = client.post(f"/api/admin/applications/{app['id']}/stage", json={"stage": 5, "note": "", "notify": False})
    assert (moved.json()["stage_name"], moved.json()["status"]) == ("Started work ✓", "completed")
    letter = client.post(f"/api/admin/applications/{app['id']}/letter")
    assert letter.status_code == 200, letter.text


def test_remote_fees(client: TestClient, setup: dict[str, Any]) -> None:
    fees = client.get("/api/admin/fees").json()
    assert fees["defaults"]["remote"] == 100000
    assert [f["name"] for f in fees["remote_jobs"]] == ["Frontend Developer"]
    assert [f["name"] for f in fees["vacancies"]] == ["Site Supervisor"]
    saved = client.put("/api/admin/fees", json={"remote": {setup["job"]["id"]: 250000}})
    assert saved.json()["remote_jobs"][0]["effective_poisha"] == 250000
    # A remote role's fee is not changed through Job Processing.
    assert client.put("/api/admin/fees", json={"job": {setup["job"]["id"]: 300000}}).status_code == 404
    assert client.get("/api/settings/public").json()["default_fee_poisha"]["remote"] == 100000


def test_success_stories_are_made_from_completed_cases(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    from app.routers.success import short_name

    assert (short_name("Rahim Uddin Khan"), short_name("Mitu"), short_name(" ")) == ("Rahim K.", "Mitu", "A client")
    before = client.get("/api/success-stories").json()
    remote = next(s for s in before["summary"] if s["module"] == "remote")
    assert (remote["completed"], remote["finished"], remote["percent"]) == (0, 0, None)

    app = apply(client, setup["job"]["slug"]).json()
    client.post(f"/api/admin/applications/{app['id']}/stage", json={"stage": 5, "note": "", "notify": False})
    after = client.get("/api/success-stories").json()
    remote = next(s for s in after["summary"] if s["module"] == "remote")
    assert (remote["completed"], remote["finished"], remote["percent"]) == (1, 1, 100)
    story = after["stories"][0]
    assert (story["name"], story["module"], story["title"], story["detail"], story["country"]) == (
        "Test P.", "remote", "Frontend Developer", "Test Remote Ltd", "UK"
    )
    # Nothing that identifies the person beyond the short name.
    assert set(story) == {"id", "name", "module", "module_label", "title", "detail", "country", "completed_at"}

    license_modules(conn, "course", "study", "job", "visa")
    assert all(s["module"] != "remote" for s in client.get("/api/success-stories").json()["stories"])


def test_remote_agent_answers_from_the_database_without_the_form(
    client: TestClient, conn: Connection, setup: dict[str, Any], settings_body: Callable[..., dict[str, Any]]
) -> None:
    def ask(question: str) -> str:
        response = client.post("/api/agent/remote/ask", json={"question": question, "inputs": None})
        assert response.status_code == 200, response.text
        return str(response.json()["answer"])

    assert ask("Which remote jobs do you have?") == (
        "We have 1 open remote job: Frontend Developer at Test Remote Ltd (UK). Fill in the form to see your match."
    )
    assert ask("What is the fee?") == "Our application fee is ৳1,000 for every open remote job. You pay it after you apply."
    assert ask("Which countries?") == "We have open remote jobs in: UK."
    steps = ask("What are the steps?")
    assert "6 stages: Application started → Profile screening" in steps and "Started work ✓" in steps
    assert "Portfolio or work samples" in ask("What documents do I need?")
    assert ask("Tell me about Frontend Developer").startswith("Frontend Developer at Test Remote Ltd is open now.")
    assert ask("hello") == "Please fill in the form first so I can match you. After that, ask me about salary, requirements, fees or the process."

    # With no open remote job, it says so and gives the contact details from Settings.
    client.put(f"/api/admin/remote-jobs/{setup['job']['id']}", json=remote_body(closed=True))
    client.put("/api/settings", json=settings_body(phone="+880 1700-000000", email="hello@agency.example"))
    empty = ask("Which remote jobs do you have?")
    assert empty.startswith("We have no open remote jobs right now.")
    assert "+880 1700-000000" in empty and "hello@agency.example" in empty
    assert "+880 1700-000000" in ask("How can I contact you?")
