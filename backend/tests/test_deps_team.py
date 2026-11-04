"""b27 (require_section) and b28 (team rules)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.auth.deps import require_section
from auth_helpers import license_modules, sign_in_admin_on, sign_in_existing_admin_on
from conftest import insert_admin, new_client


@pytest.fixture
def section_client(api: FastAPI) -> Iterator[TestClient]:
    """The app plus a test-only route behind require_section("job")."""
    api.add_api_route("/api/_test/section/job", lambda: {"ok": True}, methods=["GET"],
                      dependencies=[Depends(require_section("job"))])
    with new_client(api) as client:
        yield client


# ---------- b27 ----------


def test_require_section(section_client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    assert section_client.get("/api/_test/section/job").status_code == 401

    sign_in_admin_on(section_client, conn, "admin", ["study"])
    refused = section_client.get("/api/_test/section/job")
    assert refused.status_code == 403 and refused.json()["code"] == "FORBIDDEN"

    sign_in_admin_on(section_client, conn, "admin", ["job"])
    assert section_client.get("/api/_test/section/job").status_code == 200

    sign_in_admin_on(section_client, conn, "finance", ["job"])
    assert section_client.get("/api/_test/section/job").status_code == 403

    sign_in_admin_on(section_client, conn, "super_admin")
    assert section_client.get("/api/_test/section/job").status_code == 200

    license_modules(conn, "study")
    unlicensed = section_client.get("/api/_test/section/job")
    assert unlicensed.status_code == 403 and unlicensed.json()["code"] == "MODULE_NOT_LICENSED"


# ---------- b28 ----------


def _team(client: TestClient, admin_id: Any, action: str) -> Any:
    return client.post(f"/api/admin/team/{admin_id}/{action}")


def _role(client: TestClient, admin_id: Any, role: str) -> Any:
    return client.put(f"/api/admin/team/{admin_id}/role", json={"role": role})


def test_last_super_admin_and_self_changes(
    api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    me = act_as("super_admin")
    for refused in (_team(client, me.id, "deactivate"), _role(client, me.id, "admin")):
        assert refused.status_code == 409
        assert refused.json()["code"] == "CONFLICT"

    other_id, _ = insert_admin(conn, "admin")
    assert _role(client, other_id, "super_admin").status_code == 200
    with new_client(api) as other:
        sign_in_existing_admin_on(other, conn, other_id)
        self_change = _role(other, other_id, "admin")
        assert self_change.status_code == 403 and self_change.json()["code"] == "FORBIDDEN"
        assert _team(other, other_id, "deactivate").status_code == 403

        assert _team(client, other_id, "deactivate").status_code == 200
        assert other.get("/api/admin/team").status_code == 401
        assert other.get("/api/auth/session").json()["admin"] is None


def test_team_has_no_delete(client: TestClient, conn: Connection, act_as: Callable[..., Any], api: FastAPI) -> None:
    act_as("super_admin")
    other_id, _ = insert_admin(conn, "admin")
    assert client.delete(f"/api/admin/team/{other_id}").status_code in (404, 405)
    for route in api.routes:
        methods = getattr(route, "methods", set()) or set()
        assert not ("DELETE" in methods and "/admin/team" in getattr(route, "path", ""))
    assert conn.execute(text("SELECT count(*) FROM admin_users WHERE id = :id"), {"id": other_id}).scalar_one() == 1


def test_approve_role_sections_reactivate(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> None:
    license_modules(conn, "study", "job")
    act_as("super_admin")
    pending_id = conn.execute(
        text(
            "INSERT INTO admin_users (name, email, password_hash, role) "
            "VALUES ('Pending', 'pending@example.test', 'x', 'admin') RETURNING id"
        )
    ).scalar_one()

    approved = _team(client, pending_id, "approve")
    assert approved.status_code == 200
    assert (approved.json()["role"], approved.json()["sections"]) == ("admin", ["study", "job"])
    assert _team(client, pending_id, "approve").status_code == 409

    sections = client.put(f"/api/admin/team/{pending_id}/sections", json={"sections": ["job"]})
    assert sections.json()["sections"] == ["job"]
    assert client.put(f"/api/admin/team/{pending_id}/sections", json={"sections": ["other"]}).status_code == 422

    finance = _role(client, pending_id, "finance")
    assert (finance.json()["role"], finance.json()["sections"]) == ("finance", [])
    assert _role(client, pending_id, "owner").status_code == 422

    assert _team(client, pending_id, "deactivate").json()["active"] is False
    assert _team(client, pending_id, "deactivate").status_code == 409
    assert _team(client, pending_id, "reactivate").json()["active"] is True
    assert _team(client, pending_id, "reactivate").status_code == 409

    listed = client.get("/api/admin/team")
    assert listed.status_code == 200
    assert any(row["id"] == str(pending_id) for row in listed.json())
    assert _team(client, "not-a-uuid", "approve").status_code == 404


def test_team_needs_super_admin(client: TestClient, act_as: Callable[..., Any]) -> None:
    assert client.get("/api/admin/team").status_code == 401
    act_as("admin")
    assert client.get("/api/admin/team").status_code == 403
    act_as("finance")
    assert client.get("/api/admin/team").status_code == 403


def test_staff_list_for_assigning(api: Any, client: Any, conn: Any, act_as: Any) -> None:
    """GET /admin/staff: active, approved, non-finance staff (names and sections only)."""
    from auth_helpers import sign_in_admin_on
    from conftest import insert_admin, new_client

    act_as("admin")
    insert_admin(conn, "finance", name="Money Person")
    insert_admin(conn, "admin", ["job"], name="Job Person")
    staff = client.get("/api/admin/staff").json()
    names = [s["name"] for s in staff]
    assert "Job Person" in names and "Money Person" not in names
    assert set(staff[0]) == {"id", "name", "role", "sections"}
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.get("/api/admin/staff").json()["code"] == "FORBIDDEN"
