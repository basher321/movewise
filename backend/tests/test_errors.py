"""b04 plus the shared error format and the 3 MB size limit.

The routes used here are added only inside these tests.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import ApiError
from app.main import MAX_BODY_BYTES
from conftest import new_client


class Payload(BaseModel):
    name: str


@pytest.fixture
def test_client(api: FastAPI) -> Iterator[TestClient]:
    @api.post("/api/_test/echo")
    def echo(payload: Payload) -> dict[str, str]:
        return {"name": payload.name}

    @api.get("/api/_test/boom")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    @api.get("/api/_test/conflict")
    def conflict() -> None:
        raise ApiError("CONFLICT", 409, "Already exists.")

    with new_client(api) as client:
        yield client


def test_bad_json_is_validation(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/_test/echo", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert set(body) == {"code", "message"}


def test_missing_field_names_the_field(test_client: TestClient) -> None:
    response = test_client.post("/api/_test/echo", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert "name" in response.json()["message"]


def test_unexpected_error_is_internal_without_details(test_client: TestClient) -> None:
    response = test_client.get("/api/_test/boom")
    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL", "message": "Something went wrong."}
    assert "Traceback" not in response.text
    assert "must not leak" not in response.text


def test_api_error_uses_its_code_and_status(test_client: TestClient) -> None:
    response = test_client.get("/api/_test/conflict")
    assert response.status_code == 409
    assert response.json() == {"code": "CONFLICT", "message": "Already exists."}


def test_unknown_route_is_not_found(test_client: TestClient) -> None:
    response = test_client.get("/api/no-such-route")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_body_over_3_mb_is_refused(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/_test/echo",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"code": "VALIDATION", "message": "Request body is larger than 3 MB."}
