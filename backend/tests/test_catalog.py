"""B04: catalog, fees, match and agent answers (b32-b44). All data is made inside the test."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import audit_count, license_modules

ALL = ("course", "study", "job")


def group_body(**changes: Any) -> dict[str, Any]:
    return {"name": "Artificial Intelligence", "description": "Practical tracks", "sort_order": 1, "active": True, **changes}


def course_body(group_id: str, /, **changes: Any) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "title": "Applied Machine Learning",
        "icon": "🤖",
        "colour": "#4F46E5",
        "price_poisha": 1_200_000,
        "duration": "12 weeks",
        "level": "Intermediate",
        "description": "Build and ship models.",
        "learn_points": ["Train models", "Deploy models"],
        "syllabus": ["Week 1: Python", "Week 2: Models"],
        "published": True,
        **changes,
    }


def university_body(**changes: Any) -> dict[str, Any]:
    return {
        "name": "Test University of Toronto",
        "country": "Canada",
        "city": "Toronto",
        "levels": ["Bachelor"],
        "fields": ["Computer Science"],
        "tuition_usd": 20000,
        "min_gpa": 3.0,
        "min_ielts": 6.5,
        "intakes": "September",
        "deadline_text": "1 March",
        "scholarships": "Merit awards",
        "work_rights": "20 hours a week",
        "conditions": "",
        "apply_link": "https://apply.example.test",
        "admissions_email": "admissions@example.test",
        "fee_override_poisha": None,
        "published": True,
        **changes,
    }


def vacancy_body(**changes: Any) -> dict[str, Any]:
    return {
        "title": "Site Supervisor",
        "employer": "Test Contracting",
        "country": "UAE",
        "occupation": "Construction",
        "min_experience": 3,
        "min_education": 1,
        "min_english": 0,
        "salary_usd": 900,
        "seats": 5,
        "apply_by": (date.today() + timedelta(days=60)).isoformat(),
        "contract": "2 years",
        "benefits": "Housing",
        "conditions": "",
        "employer_licence": "LIC-1",
        "employer_email": "hr@example.test",
        "employer_verified": True,
        "closed": False,
        "fee_override_poisha": None,
        **changes,
    }


@pytest.fixture
def owner(conn: Connection, act_as: Callable[..., Any]) -> None:
    license_modules(conn, *ALL)
    act_as("super_admin")


def make_course(client: TestClient, **changes: Any) -> dict[str, Any]:
    group = client.post("/api/admin/course-groups", json=group_body())
    assert group.status_code == 200, group.text
    course = client.post("/api/admin/courses", json=course_body(group.json()["id"], **changes))
    assert course.status_code == 200, course.text
    return dict(course.json())


def make(client: TestClient, kind: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(f"/api/admin/{kind}", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


# b32
def test_b32_catalog_tables_exist_and_are_empty_before_the_test(conn: Connection) -> None:
    for table in ("course_groups", "courses", "universities", "vacancies"):
        assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


# b33
def test_b33_module_lock(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> None:
    license_modules(conn, "study")
    for path in ("/api/courses", "/api/vacancies", "/api/courses/x", "/api/vacancies/x"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["code"] == "MODULE_NOT_LICENSED"
    assert client.get("/api/universities").json() == []
    act_as("super_admin")
    for path in ("/api/admin/courses", "/api/admin/course-groups", "/api/admin/vacancies"):
        assert client.get(path).json()["code"] == "MODULE_NOT_LICENSED"
    assert client.post("/api/admin/course-groups", json=group_body()).json()["code"] == "MODULE_NOT_LICENSED"
    assert client.get("/api/admin/universities").status_code == 200


# b34
def test_b34_course_created_in_poisha_and_unpublish_hides(client: TestClient, owner: None) -> None:
    course = make_course(client)
    assert course["price_poisha"] == 1_200_000
    groups = client.get("/api/courses").json()
    assert [g["name"] for g in groups] == ["Artificial Intelligence"]
    assert groups[0]["courses"][0]["slug"] == "applied-machine-learning"
    assert client.get(f"/api/courses/{course['slug']}").status_code == 200

    hidden = client.put(f"/api/admin/courses/{course['id']}", json=course_body(course["group_id"], published=False))
    assert hidden.status_code == 200
    assert client.get("/api/courses").json() == []
    assert client.get(f"/api/courses/{course['slug']}").json()["code"] == "NOT_FOUND"
    assert len(client.get("/api/admin/courses").json()) == 1


def test_course_validation(client: TestClient, owner: None) -> None:
    group_id = client.post("/api/admin/course-groups", json=group_body()).json()["id"]
    bad = [
        {"price_poisha": 0},
        {"price_poisha": 1_200_050},
        {"price_poisha": 12.5},
        {"title": "  "},
        {"colour": "blue"},
        {"learn_points": [" "]},
        {"syllabus": []},
        {"group_id": "not-a-group"},
        {"icon": "AB"},
    ]
    for change in bad:
        response = client.post("/api/admin/courses", json=course_body(group_id, **change))
        assert response.status_code == 422, change
        assert response.json()["code"] == "VALIDATION"


def test_group_with_published_courses_cannot_be_hidden(client: TestClient, owner: None) -> None:
    course = make_course(client)
    response = client.put(f"/api/admin/course-groups/{course['group_id']}", json=group_body(active=False))
    assert response.status_code == 409
    client.put(f"/api/admin/courses/{course['id']}", json=course_body(course["group_id"], published=False))
    assert client.put(f"/api/admin/course-groups/{course['group_id']}", json=group_body(active=False)).status_code == 200


# b35
def test_b35_hidden_vacancies(client: TestClient, owner: None) -> None:
    make(client, "vacancies", vacancy_body(title="Unverified", employer_verified=False))
    make(client, "vacancies", vacancy_body(title="Closed", closed=True))
    shown = make(client, "vacancies", vacancy_body(title="Open"))
    assert [v["title"] for v in client.get("/api/vacancies").json()] == ["Open"]
    match = client.post("/api/match/job", json=job_input()).json()
    assert [m["item"]["title"] for m in match] == ["Open"]
    assert len(client.get("/api/admin/vacancies").json()) == 3
    assert client.get("/api/vacancies/unverified").status_code == 404
    public = client.get(f"/api/vacancies/{shown['slug']}").json()
    assert "employer_email" not in public and "employer_licence" not in public


def test_public_university_hides_staff_fields(client: TestClient, owner: None) -> None:
    uni = make(client, "universities", university_body())
    public = client.get(f"/api/universities/{uni['slug']}").json()
    for field in ("apply_link", "admissions_email", "fee_override_poisha", "published"):
        assert field not in public
    assert public["fee_poisha"] == 100000


def study_input(**changes: Any) -> dict[str, Any]:
    return {"level": "Bachelor", "field": "Computer Science", "gpa": 3.5, "ielts": 7, "budget_usd": 25000, **changes}


def job_input(**changes: Any) -> dict[str, Any]:
    return {
        "occupation": "Construction",
        "country": "Any country",
        "experience": 5,
        "education": "SSC / HSC",
        "english": "Basic",
        "passport_ready": True,
        "salary_goal_usd": None,
        **changes,
    }


# b36
@pytest.mark.parametrize(
    ("changes", "percent", "labels"),
    [
        ({}, 100, ["GPA meets 3", "IELTS meets 6.5", "Within budget"]),
        ({"gpa": 2.5}, 75, ["GPA below 3", "IELTS meets 6.5", "Within budget"]),
        ({"ielts": 0, "budget_usd": 10000}, 55, ["GPA meets 3", "IELTS 6.5 needed", "Above budget (~$20,000)"]),
    ],
)
def test_b36_match_study(client: TestClient, owner: None, changes: dict[str, Any], percent: int, labels: list[str]) -> None:
    make(client, "universities", university_body())
    make(client, "universities", university_body(name="Other Field", fields=["Business"]))
    make(client, "universities", university_body(name="Hidden", published=False))
    result = client.post("/api/match/study", json=study_input(**changes)).json()
    assert len(result) == 1
    assert result[0]["match_percent"] == percent
    assert [c["label"] for c in result[0]["checks"]] == labels
    assert "apply_link" not in result[0]["item"]


def test_match_study_preferred_country(client: TestClient, owner: None) -> None:
    make(client, "universities", university_body(name="In China", country="China"))
    make(client, "universities", university_body(name="In Malaysia", country="Malaysia"))
    make(client, "universities", university_body(name="Hidden", country="Japan", published=False))

    def names(**changes: Any) -> list[str]:
        return sorted(m["item"]["name"] for m in client.post("/api/match/study", json=study_input(**changes)).json())

    assert names() == ["In China", "In Malaysia"]
    assert names(country="Any country") == ["In China", "In Malaysia"]
    assert names(country="China") == ["In China"]
    assert names(country="Japan") == []
    assert client.get("/api/catalog/options").json()["study_countries"] == ["Any country", "China", "Malaysia"]


def test_match_study_input_and_empty(client: TestClient, owner: None) -> None:
    assert client.post("/api/match/study", json=study_input()).json() == []
    assert client.post("/api/match/study", json=study_input(gpa=5)).json()["code"] == "VALIDATION"
    assert client.post("/api/match/study", json=study_input(level="")).json()["code"] == "VALIDATION"


# b37
def test_b37_match_job_country_and_salary(client: TestClient, owner: None) -> None:
    make(client, "vacancies", vacancy_body(title="UAE job", country="UAE", salary_usd=900))
    make(client, "vacancies", vacancy_body(title="Japan job", country="Japan", salary_usd=1700))
    any_country = client.post("/api/match/job", json=job_input()).json()
    assert {m["item"]["title"] for m in any_country} == {"UAE job", "Japan job"}
    japan = client.post("/api/match/job", json=job_input(country="Japan")).json()
    assert [m["item"]["title"] for m in japan] == ["Japan job"]
    assert japan[0]["match_percent"] == 100

    goal = client.post("/api/match/job", json=job_input(country="UAE", salary_goal_usd=1000, passport_ready=False)).json()
    labels = [c["label"] for c in goal[0]["checks"]]
    assert labels[-2:] == ["Passport must be valid 18+ months", "Pays ~$900/month"]
    # 2 + 1.5 + 1 of 7.5 -> 30 + 70 * 4.5 / 7.5 = 72
    assert goal[0]["match_percent"] == 72
    assert client.post("/api/match/job", json=job_input(education="PhD")).json()["code"] == "VALIDATION"


# b38
def test_b38_effective_fee(client: TestClient, owner: None) -> None:
    uni = make(client, "universities", university_body())
    vac = make(client, "vacancies", vacancy_body())
    fees = client.get("/api/admin/fees").json()
    assert fees["defaults"] == {"study": 100000, "job": 100000, "visa": 100000, "remote": 100000}
    assert fees["universities"][0]["effective_poisha"] == 100000

    saved = client.put("/api/admin/fees", json={"study": {uni["id"]: 250000}, "job": {vac["id"]: 100000}})
    assert saved.status_code == 200
    body = saved.json()
    assert body["universities"][0]["override_poisha"] == 250000
    assert body["vacancies"][0]["override_poisha"] is None
    assert client.get(f"/api/universities/{uni['slug']}").json()["fee_poisha"] == 250000

    for bad in (0, 12.5, -100):
        response = client.put("/api/admin/fees", json={"study": {uni["id"]: bad}})
        assert response.status_code == 422, bad

    reset = client.post("/api/admin/fees/reset", json={"scope": "all"}).json()
    assert reset["universities"][0]["override_poisha"] is None
    assert client.get(f"/api/universities/{uni['slug']}").json()["fee_poisha"] == 100000


# b39
@pytest.mark.parametrize("changes", [{"min_gpa": 5}, {"min_ielts": 6.3}, {"apply_link": "http://x.test"}, {"levels": []}, {"admissions_email": "nope"}])
def test_b39_university_validation(client: TestClient, owner: None, changes: dict[str, Any]) -> None:
    response = client.post("/api/admin/universities", json=university_body(**changes))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"


def test_vacancy_validation(client: TestClient, owner: None) -> None:
    past = (date.today() - timedelta(days=3)).isoformat()
    for change in ({"salary_usd": 0}, {"min_experience": -1}, {"seats": 0}, {"apply_by": past}, {"min_education": 4}):
        assert client.post("/api/admin/vacancies", json=vacancy_body(**change)).status_code == 422, change
    # A past date is allowed while the vacancy is closed.
    assert client.post("/api/admin/vacancies", json=vacancy_body(apply_by=past, closed=True)).status_code == 200


# b40
@pytest.mark.parametrize("role", ["admin", "finance"])
def test_b40_only_super_admin(client: TestClient, conn: Connection, act_as: Callable[..., Any], role: str) -> None:
    license_modules(conn, *ALL)
    act_as(role)
    calls = [
        ("get", "/api/admin/course-groups", None),
        ("post", "/api/admin/course-groups", group_body()),
        ("get", "/api/admin/courses", None),
        ("get", "/api/admin/universities", None),
        ("post", "/api/admin/universities", university_body()),
        ("get", "/api/admin/vacancies", None),
        ("post", "/api/admin/vacancies", vacancy_body()),
        ("get", "/api/admin/fees", None),
        ("put", "/api/admin/fees", {"study": {}}),
        ("post", "/api/admin/fees/reset", {"scope": "all"}),
    ]
    for method, path, body in calls:
        response = client.request(method, path, json=body)
        assert response.status_code == 403, path
        assert response.json()["code"] == "FORBIDDEN", path


def test_signed_out_admin_endpoints(client: TestClient, conn: Connection) -> None:
    license_modules(conn, *ALL)
    assert client.get("/api/admin/courses").json()["code"] == "UNAUTHENTICATED"
    assert client.get("/api/admin/fees").json()["code"] == "UNAUTHENTICATED"


# b41
def test_b41_no_delete_routes(api: FastAPI) -> None:
    for route in api.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if any(word in path for word in ("course", "universit", "vacanc", "fees", "catalog")):
            assert "DELETE" not in methods, path


# b42
def test_b42_audit_rows(client: TestClient, conn: Connection, owner: None) -> None:
    before = audit_count(conn)
    vac = make(client, "vacancies", vacancy_body(employer_verified=False))
    assert audit_count(conn) == before + 1

    client.put(f"/api/admin/vacancies/{vac['id']}", json=vacancy_body(employer_verified=True))
    assert audit_count(conn, "Employer verified") == 1
    assert audit_count(conn) == before + 2

    client.put(f"/api/admin/vacancies/{vac['id']}", json=vacancy_body(employer_verified=True, salary_usd=950))
    assert audit_count(conn) == before + 3
    details = conn.execute(text("SELECT detail FROM audit_log WHERE action = 'catalog.vacancy_saved'")).scalars().all()
    assert "Site Supervisor: salary_usd" in details

    client.put(f"/api/admin/vacancies/{vac['id']}", json=vacancy_body(employer_verified=False))
    assert audit_count(conn, "Employer unverified") == 1


# b43
def test_b43_slugs(client: TestClient, owner: None) -> None:
    first = make(client, "universities", university_body(name="Same Name University"))
    second = make(client, "universities", university_body(name="Same Name University"))
    assert first["slug"] == "same-name-university"
    assert second["slug"].startswith("same-name-university-") and second["slug"] != first["slug"]
    renamed = client.put(f"/api/admin/universities/{first['id']}", json=university_body(name="New Name")).json()
    assert renamed["slug"] == "same-name-university"


# b44
def test_b44_agent(client: TestClient, conn: Connection, owner: None) -> None:
    make(client, "universities", university_body())
    plain = client.post("/api/agent/study/ask", json={"question": "Hello", "inputs": None}).json()
    assert plain["answer"].startswith("Please fill in the form first")
    answer = client.post("/api/agent/study/ask", json={"question": "What does it cost?", "inputs": study_input()}).json()
    assert "costs about $20,000 per year" in answer["answer"]
    assert client.post("/api/agent/study/ask", json={"question": "  ", "inputs": None}).status_code == 422
    assert client.post("/api/agent/course/ask", json={"question": "x"}).status_code == 404
    license_modules(conn, "job")
    response = client.post("/api/agent/study/ask", json={"question": "Hi", "inputs": None})
    assert response.status_code == 403
    assert response.json()["code"] == "MODULE_NOT_LICENSED"


def test_catalog_options(client: TestClient, conn: Connection, owner: None) -> None:
    make(client, "universities", university_body(levels=["Master", "Bachelor"]))
    make(client, "vacancies", vacancy_body(country="Japan", occupation="Electrician"))
    options = client.get("/api/catalog/options").json()
    assert options["study_levels"] == ["Bachelor", "Master"]
    assert options["study_fields"] == ["Computer Science"]
    assert options["occupations"] == ["Electrician"]
    countries = options["countries"]
    assert countries[0] == "Any country" and len(countries) == len(set(countries)) > 190
    assert {"Japan", "Saudi Arabia", "UAE", "UK", "USA", "Malaysia", "Bangladesh"} <= set(countries)
    assert countries[1:] == sorted(countries[1:], key=str.casefold)
    make(client, "vacancies", vacancy_body(country="Faroe Islands", occupation="Fisher"))
    assert "Faroe Islands" in client.get("/api/catalog/options").json()["countries"]
    assert options["education_levels"][0] == "Below SSC"
    license_modules(conn, "study")
    assert client.get("/api/catalog/options").json()["occupations"] == []
    assert client.get("/api/catalog/options").json()["countries"] == []


def test_admin_vacancy_flags_past_apply_by(client: TestClient, conn: Connection, owner: None) -> None:
    vac = make(client, "vacancies", vacancy_body())
    conn.execute(text("UPDATE vacancies SET apply_by = current_date - 2 WHERE id = :id"), {"id": vac["id"]})
    listed = client.get("/api/admin/vacancies").json()[0]
    assert listed["past_apply_by"] is True
    assert len(client.get("/api/vacancies").json()) == 1


def test_success_rate_counts_finished_journeys(client: TestClient, conn: Connection, owner: None) -> None:
    from auth_helpers import verified_applicant

    vac = make(client, "vacancies", vacancy_body())
    assert client.get(f"/api/vacancies/{vac['slug']}").json()["success_rate"] is None
    verified_applicant(client, conn, "job", "rate@example.test")

    def finish(status: str) -> None:
        response = client.post("/api/me/job/applications", json={"item_slug": vac["slug"], "answers": {}})
        assert response.status_code == 200, response.text
        conn.execute(text("UPDATE applications SET status = :s WHERE id = :id"), {"s": status, "id": response.json()["id"]})

    # Completed and rejected journeys are finished; a withdrawn or open case is not counted.
    for status in ("completed", "completed", "rejected", "withdrawn", "active"):
        finish(status)
    rate = client.get(f"/api/vacancies/{vac['slug']}").json()["success_rate"]
    assert rate == {"percent": 67, "completed": 2, "finished": 3}
    listed = [v for v in client.get("/api/vacancies").json() if v["slug"] == vac["slug"]]
    assert listed[0]["success_rate"] == rate
    admin = [v for v in client.get("/api/admin/vacancies").json() if v["id"] == vac["id"]]
    assert admin[0]["success_rate"] == rate
