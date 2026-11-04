"""B05: applications, stages, status, case handling, history and case emails (b45-b57)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import insert_admin, new_client
from test_catalog import university_body, vacancy_body

ALL = ("course", "study", "job")


@pytest.fixture
def setup(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    """Licence on, a super admin, one university and one vacancy, and a signed-in applicant per module."""
    license_modules(conn, *ALL)
    act_as("super_admin")
    uni = client.post("/api/admin/universities", json=university_body(admissions_email="")).json()
    vac = client.post("/api/admin/vacancies", json=vacancy_body()).json()
    verified_applicant(client, conn, "study", "student@example.test")
    verified_applicant(client, conn, "job", "worker@example.test")
    return {"uni": uni, "vac": vac}


def apply(client: TestClient, module: str, slug: str, answers: dict[str, Any] | None = None) -> Any:
    return client.post(f"/api/me/{module}/applications", json={"item_slug": slug, "answers": answers or {}})


def study_app(client: TestClient, setup: dict[str, Any]) -> dict[str, Any]:
    response = apply(client, "study", setup["uni"]["slug"], {"level": "Bachelor", "gpa": 3.5})
    assert response.status_code == 200, response.text
    return dict(response.json())


def job_app(client: TestClient, setup: dict[str, Any]) -> dict[str, Any]:
    response = apply(client, "job", setup["vac"]["slug"], {"passport_ready": True, "salary_goal_usd": None})
    assert response.status_code == 200, response.text
    return dict(response.json())


# b45
def test_b45_events_cannot_change(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    for sql in ("UPDATE app_events SET text = 'x'", "DELETE FROM app_events WHERE application_id = :id"):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql), {"id": app["id"]})


def test_new_application(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    assert app["ref"].startswith("APP-")
    assert (app["stage"], app["status"], app["stage_name"], app["stage_count"]) == (0, "active", "Application started", 9)
    assert app["fee_poisha"] == 100000
    assert [e["text"] for e in app["history"]] == ["Application started"]
    subject = conn.execute(
        text("SELECT subject FROM notifications WHERE event = 'application_received'")
    ).scalar_one()
    assert subject == f"Application received - {app['ref']}"
    listed = client.get("/api/me/study/applications").json()
    assert [a["item_title"] for a in listed] == ["Test University of Toronto"]


# b46
def test_b46_apply_twice_and_after_withdraw(client: TestClient, setup: dict[str, Any]) -> None:
    first = study_app(client, setup)
    assert study_app(client, setup)["id"] == first["id"]
    withdrawn = client.post(f"/api/me/study/applications/{first['id']}/withdraw").json()
    assert withdrawn["status"] == "withdrawn"
    assert client.post(f"/api/me/study/applications/{first['id']}/withdraw").status_code == 409
    assert study_app(client, setup)["id"] != first["id"]


# b47
@pytest.mark.parametrize("answers", [{"colour": "red"}, {"gpa": "high"}, {"level": 3}, {"gpa": True}, {"level": "x" * 5000}])
def test_b47_answers_checked(client: TestClient, setup: dict[str, Any], answers: dict[str, Any]) -> None:
    response = apply(client, "study", setup["uni"]["slug"], answers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"


def test_job_answers_types(client: TestClient, setup: dict[str, Any]) -> None:
    assert apply(client, "job", setup["vac"]["slug"], {"passport_ready": "yes"}).status_code == 422
    assert apply(client, "job", setup["vac"]["slug"], {"level": "Bachelor"}).status_code == 422


def test_hidden_item_cannot_be_applied_to(client: TestClient, setup: dict[str, Any]) -> None:
    client.put(f"/api/admin/universities/{setup['uni']['id']}", json=university_body(admissions_email="", published=False))
    assert apply(client, "study", setup["uni"]["slug"]).status_code == 404
    # Not signed in to Training: "signed in" is checked first.
    assert apply(client, "course", "anything").status_code == 401


# b48
def test_b48_other_applicants_application_is_404(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    other = new_client(api)
    verified_applicant(other, conn, "study", "other@example.test")
    for call in (
        lambda: other.get(f"/api/me/study/applications/{app['id']}"),
        lambda: other.post(f"/api/me/study/applications/{app['id']}/withdraw"),
        lambda: other.get("/api/me/study/applications/not-a-uuid"),
    ):
        response = call()
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
    assert other.get("/api/me/study/applications").json() == []


# b49
def test_b49_apply_link_only_after_paying(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    detail = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert "apply_link" not in detail
    conn.execute(text("UPDATE applications SET fee_paid = true WHERE id = :id"), {"id": app["id"]})
    detail = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert detail["apply_link"] == "https://apply.example.test"
    assert detail["fee_poisha"] is None

    job = job_app(client, setup)
    conn.execute(text("UPDATE applications SET fee_paid = true WHERE id = :id"), {"id": job["id"]})
    assert "apply_link" not in client.get(f"/api/me/job/applications/{job['id']}").json()


def stage(client: TestClient, app_id: str, value: int, notify: bool = False) -> Any:
    return client.post(f"/api/admin/applications/{app_id}/stage", json={"stage": value, "note": "", "notify": notify})


def status(client: TestClient, app_id: str, value: str, reason: str = "") -> Any:
    return client.post(f"/api/admin/applications/{app_id}/status", json={"status": value, "reason": reason})


# b50
def test_b50_stages(client: TestClient, setup: dict[str, Any]) -> None:
    study = study_app(client, setup)
    assert stage(client, study["id"], 8).json()["status"] == "completed"
    job = job_app(client, setup)
    assert stage(client, job["id"], 8).status_code == 422
    assert stage(client, job["id"], 7).json()["status"] == "completed"

    again = job_app(client, setup)
    assert status(client, again["id"], "on_hold", "Waiting for passport").status_code == 200
    response = stage(client, again["id"], 2)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_stage_notify(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    before = conn.execute(text("SELECT count(*) FROM notifications")).scalar_one()
    stage(client, app["id"], 2, notify=False)
    assert conn.execute(text("SELECT count(*) FROM notifications")).scalar_one() == before
    stage(client, app["id"], 3, notify=True)
    subject = conn.execute(text("SELECT subject FROM notifications WHERE event = 'stage_changed'")).scalar_one()
    assert subject == f"Update on {app['ref']}: Offer letter received"
    history = client.get(f"/api/me/study/applications/{app['id']}").json()["history"]
    assert history[0]["text"] == "Stage -> Offer letter received"


# b51
def test_b51_status_rules(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    assert status(client, app["id"], "rejected").status_code == 422
    assert status(client, app["id"], "withdrawn", "x").status_code == 422
    done = status(client, app["id"], "rejected", "Grades too low")
    assert done.status_code == 200
    public = client.get(f"/api/me/study/applications/{app['id']}").json()["history"]
    assert public[0]["text"] == "Status -> Rejected" and public[0]["note"] == "Grades too low"
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'status_changed'")).scalar_one() == 1
    assert status(client, app["id"], "active").status_code == 422
    assert status(client, app["id"], "active", "New grades").status_code == 200

    other = job_app(client, setup)
    client.post(f"/api/me/job/applications/{other['id']}/withdraw")
    response = status(client, other["id"], "active", "Reopen")
    assert response.status_code == 409


# b52
def test_b52_patch(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = job_app(client, setup)
    events = conn.execute(text("SELECT count(*) FROM app_events")).scalar_one()
    audits = audit_count(conn)
    same = client.patch(f"/api/admin/applications/{app['id']}", json={"interview_result": "pending"}).json()
    assert same["changed"] == []
    assert conn.execute(text("SELECT count(*) FROM app_events")).scalar_one() == events
    assert audit_count(conn) == audits

    finance_id, _ = insert_admin(conn, "finance")
    response = client.patch(f"/api/admin/applications/{app['id']}", json={"assigned_to": str(finance_id)})
    assert response.status_code == 422

    study_admin, _ = insert_admin(conn, "admin", ["study"])
    assert client.patch(f"/api/admin/applications/{app['id']}", json={"assigned_to": str(study_admin)}).status_code == 422
    job_admin, _ = insert_admin(conn, "admin", ["job"], name="Rahim")
    done = client.patch(
        f"/api/admin/applications/{app['id']}",
        json={"assigned_to": str(job_admin), "interview_at": "2030-01-10T10:00:00", "offered_salary_usd": 950},
    ).json()
    assert sorted(done["changed"]) == ["assigned_to", "interview_at", "offered_salary_usd"]
    assert done["assigned_to"]["name"] == "Rahim"
    assert done["interview_at"] == "2030-01-10T10:00:00+06:00"
    assert audit_count(conn) == audits + 1
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'interview_scheduled'")).scalar_one() == 1
    mine = client.get(f"/api/me/job/applications/{app['id']}").json()
    assert mine["advisor_name"] == "Rahim"
    assert all(e["text"] != "Case updated: assigned to, interview, offered salary" for e in mine["history"])

    conn.execute(text("UPDATE admin_users SET active = false WHERE id = :id"), {"id": job_admin})
    shown = client.get(f"/api/admin/applications/{app['id']}").json()
    assert shown["assigned_to"]["name"] == "Rahim (deactivated)"


# b53
def test_b53_case_email(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    url = f"/api/admin/applications/{app['id']}/email"
    no_email = client.post(url, json={"to": "provider", "subject": "Docs", "body": "Attached"})
    assert no_email.status_code == 422
    assert "No email on file" in no_email.json()["message"]
    assert client.post(url, json={"to": "applicant", "subject": " ", "body": "x"}).status_code == 422

    job = job_app(client, setup)
    sent = client.post(
        f"/api/admin/applications/{job['id']}/email", json={"to": "provider", "subject": "Candidate", "body": "CV"}
    ).json()
    assert "hr@example.test" in [e["to"] for e in sent["emails"]]
    assert sent["history"][0]["text"] == "Email sent to employer: Candidate"
    assert sent["history"][0]["public"] is False


# b54
def test_b54_sections(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    job = job_app(client, setup)
    study = study_app(client, setup)
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    assert staff.get("/api/admin/applications?module=study").status_code == 200
    for response in (
        staff.get("/api/admin/applications?module=job"),
        staff.get(f"/api/admin/applications/{job['id']}"),
        stage(staff, job["id"], 1),
        staff.get("/api/admin/accounts?module=job"),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    for path in ("/api/admin/applications?module=job", "/api/admin/applications?module=study", f"/api/admin/applications/{study['id']}"):
        assert finance.get(path).json()["code"] == "FORBIDDEN"


def test_admin_list_filters(client: TestClient, setup: dict[str, Any]) -> None:
    app = study_app(client, setup)
    page = client.get("/api/admin/applications?module=study").json()
    assert page["total"] == 1
    row = page["items"][0]
    assert row["applicant"]["email"] == "student@example.test"
    assert row["answers"] == {"level": "Bachelor", "gpa": 3.5}
    assert client.get(f"/api/admin/applications?module=study&q={app['ref']}").json()["total"] == 1
    assert client.get("/api/admin/applications?module=study&q=nobody%25").json()["total"] == 0
    assert client.get("/api/admin/applications?module=study&status=rejected").json()["total"] == 0
    assert client.get("/api/admin/applications?module=study&assigned=none").json()["total"] == 1
    assert client.get("/api/admin/applications?module=study&assigned=me").json()["total"] == 0
    assert client.get("/api/admin/applications").status_code == 422
    accounts = client.get("/api/admin/accounts?module=study").json()
    assert [a["email"] for a in accounts] == ["student@example.test"]
    unis = client.get("/api/admin/universities").json()
    assert unis[0]["applied_count"] == 1


# b55
def test_b55_hidden_university_for_applicant_only(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    study_app(client, setup)
    client.put(f"/api/admin/universities/{setup['uni']['id']}", json=university_body(admissions_email="", published=False))
    slug = setup["uni"]["slug"]
    assert client.get(f"/api/universities/{slug}").status_code == 200
    stranger = new_client(api)
    verified_applicant(stranger, conn, "study", "stranger@example.test")
    assert stranger.get(f"/api/universities/{slug}").status_code == 404


# b56
def test_b56_two_stage_changes_keep_both_events(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    # Both requests lock the row (SELECT ... FOR UPDATE); the second waits for the first.
    # The test transaction cannot run two real transactions at once, so this checks the result:
    # both changes finish and neither event is lost.
    app = study_app(client, setup)
    assert stage(client, app["id"], 1).status_code == 200
    assert stage(client, app["id"], 2).status_code == 200
    texts = [e["text"] for e in client.get(f"/api/admin/applications/{app['id']}").json()["history"]]
    assert texts[:2] == ["Stage -> University review", "Stage -> Documents submitted"]


# b57
def test_b57_one_audit_row_per_change(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    app = job_app(client, setup)
    base = f"/api/admin/applications/{app['id']}"
    calls = [
        lambda: stage(client, app["id"], 1, notify=True),
        lambda: status(client, app["id"], "on_hold", "Medical"),
        lambda: status(client, app["id"], "active"),
        lambda: client.patch(base, json={"deadline": "2030-02-01"}),
        lambda: client.post(base + "/notes", json={"note": "Called the applicant"}),
        lambda: client.post(base + "/email", json={"to": "applicant", "subject": "Hello", "body": "Please call us"}),
        lambda: client.post(f"/api/me/job/applications/{app['id']}/withdraw"),
    ]
    for call in calls:
        before = audit_count(conn)
        response = call()
        assert response.status_code == 200, response.text
        assert audit_count(conn) == before + 1
