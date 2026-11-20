"""B24: quick verify of vacancies. All data is made inside the test."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import audit_count, license_modules, sign_in_admin_on
from test_catalog import vacancy_body

URL = "/api/admin/vacancies/verify"


@pytest.fixture
def sa(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> TestClient:
    license_modules(conn, "job", "remote")
    act_as("super_admin")
    return client


def new_vacancy(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/admin/vacancies", json=vacancy_body(employer_verified=False, **changes))
    assert response.status_code == 200, response.text
    return dict(response.json())


def is_verified(conn: Connection, vacancy_id: str) -> bool:
    return bool(conn.execute(text("SELECT employer_verified FROM vacancies WHERE id = :id"), {"id": vacancy_id}).scalar_one())


def public_ids(client: TestClient) -> set[str]:
    return {v["slug"] for v in client.get("/api/vacancies").json()}


def test_verify_puts_vacancies_on_the_public_list(sa: TestClient, conn: Connection) -> None:
    one = new_vacancy(sa, title="First Role")
    two = new_vacancy(sa, title="Second Role")
    other = new_vacancy(sa, title="Not Chosen")
    assert public_ids(sa) == set()
    audits = audit_count(conn, "Employer verified")

    response = sa.post(URL, json={"ids": [one["id"], two["id"]]})
    assert response.status_code == 200, response.text
    assert response.json() == {"verified": 2}
    assert public_ids(sa) == {one["slug"], two["slug"]}
    assert not is_verified(conn, other["id"])
    assert audit_count(conn, "Employer verified") == audits + 2


def test_only_the_verified_flag_changes(sa: TestClient, conn: Connection) -> None:
    vacancy = new_vacancy(sa)
    columns = "title, employer, country, occupation, salary_usd, seats, apply_by, closed, remote, fee_override_poisha"
    query = text(f"SELECT {columns} FROM vacancies WHERE id = :id")
    before = conn.execute(query, {"id": vacancy["id"]}).one()
    assert sa.post(URL, json={"ids": [vacancy["id"]]}).status_code == 200
    assert conn.execute(query, {"id": vacancy["id"]}).one() == before


def test_already_verified_is_not_counted_and_repeats_count_once(sa: TestClient, conn: Connection) -> None:
    vacancy = new_vacancy(sa)
    assert sa.post(URL, json={"ids": [vacancy["id"], vacancy["id"]]}).json() == {"verified": 1}
    audits = audit_count(conn, "Employer verified")
    assert sa.post(URL, json={"ids": [vacancy["id"]]}).json() == {"verified": 0}
    assert audit_count(conn, "Employer verified") == audits


def test_unknown_or_remote_id_changes_nothing(sa: TestClient, conn: Connection) -> None:
    vacancy = new_vacancy(sa)
    response = sa.post(URL, json={"ids": [vacancy["id"], str(uuid4())]})
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert not is_verified(conn, vacancy["id"])
    assert sa.post(URL, json={"ids": ["not-an-id"]}).status_code == 404

    remote = sa.post("/api/admin/remote-jobs", json=vacancy_body(employer_verified=False)).json()
    assert sa.post(URL, json={"ids": [vacancy["id"], remote["id"]]}).status_code == 404
    assert not is_verified(conn, remote["id"]) and not is_verified(conn, vacancy["id"])


def test_empty_list_is_refused(sa: TestClient) -> None:
    response = sa.post(URL, json={"ids": []})
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION"


def test_who_may_verify(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> None:
    license_modules(conn, "job")
    body = {"ids": [str(uuid4())]}
    assert client.post(URL, json=body).json()["code"] == "UNAUTHENTICATED"

    sign_in_admin_on(client, conn, "admin", ["job"])
    assert client.post(URL, json=body).json()["code"] == "FORBIDDEN"
    sign_in_admin_on(client, conn, "finance", [])
    assert client.post(URL, json=body).json()["code"] == "FORBIDDEN"

    license_modules(conn, "study")
    sign_in_admin_on(client, conn, "super_admin", [])
    response = client.post(URL, json=body)
    assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"
