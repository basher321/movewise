"""b03 and the database-down case (the password never appears in the response or log)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.db.engine import get_engine, make_engine
from app.db.migrate import MIGRATIONS_DIR


def test_health_ok(client: TestClient) -> None:
    last = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))[-1]
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "migrations": last}


def test_health_database_down(api: FastAPI, caplog: pytest.LogCaptureFixture) -> None:
    # Port 1 has no database server, so the connection always fails.
    unreachable = make_engine("postgresql+psycopg://nobody:FakePw123@127.0.0.1:1/movewise_test")

    def down_engine() -> Engine:
        return unreachable

    api.dependency_overrides[get_engine] = down_engine
    try:
        with TestClient(api, raise_server_exceptions=False) as client:
            response = client.get("/api/health")
    finally:
        unreachable.dispose()
    assert response.status_code == 503
    assert response.json()["database"] == "down"
    assert "FakePw123" not in response.text
    assert "FakePw123" not in caplog.text
