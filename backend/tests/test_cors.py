"""b05: only FRONTEND_ORIGIN gets CORS permission, with credentials."""

from fastapi.testclient import TestClient

from app.config import get_settings

OTHER_ORIGIN = "http://other-origin.invalid"


def test_other_origin_preflight_is_refused_as_json(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={"Origin": OTHER_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "message": "Origin not allowed."}
    assert "access-control-allow-origin" not in response.headers


def test_other_origin_simple_request_gets_no_permission(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": OTHER_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_frontend_origin_is_allowed_with_credentials(client: TestClient) -> None:
    origin = get_settings().frontend_origin
    response = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
