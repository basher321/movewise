"""B21: agreements and other documents of partner agents and partners."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.licence import today_dhaka
from auth_helpers import audit_count, license_modules, sign_in_admin_on
from conftest import new_client
from test_partner_agents import agent_body
from test_partners import partner_body

PDF = b"%PDF-1.4\n" + b"0" * 200
MB = 1024 * 1024


@pytest.fixture
def sa(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> TestClient:
    license_modules(conn, "course", "study", "job")
    act_as("super_admin")
    return client


def new_agent(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/admin/agents", json=agent_body(**changes))
    assert response.status_code == 200, response.text
    return dict(response.json())


def new_partner(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/admin/partners", json=partner_body(**changes))
    assert response.status_code == 200, response.text
    return dict(response.json())


def upload(
    client: TestClient,
    kind: str,
    owner_id: str,
    data: bytes = PDF,
    name: str = "agreement.pdf",
    **fields: str,
) -> Any:
    form = {"doc_type": "agreement", "title": "Signed agreement 2026", "valid_until": "", "note": ""}
    form.update(fields)
    return client.post(
        f"/api/admin/{kind}s/{owner_id}/documents", data=form, files={"file": (name, data, "application/pdf")}
    )


def docs(client: TestClient, kind: str, owner_id: str) -> Any:
    return client.get(f"/api/admin/{kind}s/{owner_id}/documents")


@pytest.mark.parametrize("kind", ["agent", "partner"])
def test_upload_list_view_archive(sa: TestClient, conn: Connection, kind: str) -> None:
    owner = new_agent(sa) if kind == "agent" else new_partner(sa)
    until = (today_dhaka() + timedelta(days=400)).isoformat()
    response = upload(sa, kind, owner["id"], valid_until=until, note="Original kept in office file 12.")
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["doc_type"] == "agreement" and doc["title"] == "Signed agreement 2026"
    assert doc["original_name"] == "agreement.pdf" and doc["mime"] == "application/pdf"
    assert doc["valid_until"] == until and doc["shown_status"] == "active" and doc["status"] == "active"
    assert doc["uploaded_by_name"] == "Test super_admin" and doc["archived_at"] is None
    assert doc["file_url"] == f"/api/admin/{kind}s/{owner['id']}/documents/{doc['id']}/file"
    assert audit_count(conn, f"{kind}_document.uploaded") == 1

    assert [d["id"] for d in docs(sa, kind, owner["id"]).json()] == [doc["id"]]

    file = sa.get(doc["file_url"])
    assert file.status_code == 200 and file.content == PDF
    assert file.headers["content-type"] == "application/pdf"
    assert file.headers["x-content-type-options"] == "nosniff"
    assert audit_count(conn, f"{kind}_document.viewed") == 1

    archived = sa.post(f"/api/admin/{kind}s/{owner['id']}/documents/{doc['id']}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived" and archived.json()["shown_status"] == "archived"
    assert archived.json()["archived_by_name"] == "Test super_admin"
    assert audit_count(conn, f"{kind}_document.archived") == 1
    again = sa.post(f"/api/admin/{kind}s/{owner['id']}/documents/{doc['id']}/archive")
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT"
    # An archived document stays listed and viewable.
    assert docs(sa, kind, owner["id"]).json()[0]["status"] == "archived"
    assert sa.get(doc["file_url"]).status_code == 200


def test_active_documents_listed_first_and_expiry_status(sa: TestClient) -> None:
    agent = new_agent(sa)
    today = today_dhaka()
    old = upload(sa, "agent", agent["id"], title="Old").json()
    sa.post(f"/api/admin/agents/{agent['id']}/documents/{old['id']}/archive")
    expired = upload(sa, "agent", agent["id"], title="Expired", valid_until=(today - timedelta(days=1)).isoformat()).json()
    expiring = upload(sa, "agent", agent["id"], title="Expiring", valid_until=(today + timedelta(days=30)).isoformat()).json()
    assert expired["shown_status"] == "expired" and expiring["shown_status"] == "expiring"
    # Archived last. (In one test transaction every row has the same upload time.)
    listed = [d["title"] for d in docs(sa, "agent", agent["id"]).json()]
    assert sorted(listed[:2]) == ["Expired", "Expiring"] and listed[2] == "Old"


def test_file_size_and_type(sa: TestClient) -> None:
    agent = new_agent(sa)
    # Larger than applicant documents (2 MB) is fine up to 10 MB.
    big = upload(sa, "agent", agent["id"], data=b"%PDF-" + b"0" * (5 * MB))
    assert big.status_code == 200, big.text
    too_big = upload(sa, "agent", agent["id"], data=b"%PDF-" + b"0" * (10 * MB))
    assert too_big.status_code == 422 and too_big.json() == {
        "code": "VALIDATION",
        "message": "The file must be from 1 byte to 10 MB.",
    }
    way_too_big = upload(sa, "agent", agent["id"], data=b"%PDF-" + b"0" * (11 * MB))
    assert way_too_big.status_code == 422 and way_too_big.json()["message"] == "The file must be 10 MB or smaller."
    assert upload(sa, "agent", agent["id"], data=b"just text", name="a.pdf").json()["message"] == "Only PDF, JPG or PNG files."
    assert upload(sa, "agent", agent["id"], data=b"\x89PNG\r\n\x1a\n" + b"0" * 50, name="scan.png").status_code == 200
    # Other endpoints keep the 3 MB body limit.
    assert sa.post("/api/admin/agents", content=b"x" * (4 * MB)).json()["message"] == "Request body is larger than 3 MB."


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"doc_type": "contract"}, "Please choose the document type."),
        ({"doc_type": ""}, "Please choose the document type."),
        ({"valid_until": "31/12/2027"}, "Valid until must be a date like 2027-12-31."),
        ({"title": "x" * 121}, "The title must be at most 120 characters."),
        ({"note": "x" * 501}, "The note must be at most 500 characters."),
    ],
)
def test_input_checked(sa: TestClient, fields: dict[str, str], message: str) -> None:
    agent = new_agent(sa)
    response = upload(sa, "agent", agent["id"], **fields)
    assert response.status_code == 422 and response.json() == {"code": "VALIDATION", "message": message}
    assert docs(sa, "agent", agent["id"]).json() == []


def test_missing_file(sa: TestClient) -> None:
    agent = new_agent(sa)
    response = sa.post(f"/api/admin/agents/{agent['id']}/documents", data={"doc_type": "agreement"})
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION"


def test_agent_documents_who_may(api: FastAPI, sa: TestClient, conn: Connection) -> None:
    agent = new_agent(sa, sections=["study"])
    doc = upload(sa, "agent", agent["id"]).json()

    study_admin = new_client(api)
    sign_in_admin_on(study_admin, conn, "admin", ["study"])
    assert docs(study_admin, "agent", agent["id"]).status_code == 200
    assert study_admin.get(doc["file_url"]).status_code == 200
    # Admins cannot edit agents, so they cannot upload or archive their documents.
    assert upload(study_admin, "agent", agent["id"]).json()["code"] == "FORBIDDEN"
    archive = study_admin.post(f"/api/admin/agents/{agent['id']}/documents/{doc['id']}/archive")
    assert archive.json()["code"] == "FORBIDDEN"

    job_admin = new_client(api)
    sign_in_admin_on(job_admin, conn, "admin", ["job"])
    assert docs(job_admin, "agent", agent["id"]).json()["code"] == "FORBIDDEN"
    assert job_admin.get(doc["file_url"]).json()["code"] == "FORBIDDEN"

    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert docs(finance, "agent", agent["id"]).json()["code"] == "FORBIDDEN"

    anon = new_client(api)
    anon.cookies.clear()
    assert docs(anon, "agent", agent["id"]).status_code == 401
    assert anon.get(doc["file_url"]).status_code == 401


def test_partner_documents_who_may(api: FastAPI, sa: TestClient, conn: Connection) -> None:
    partner = new_partner(sa, module="study")
    study_admin = new_client(api)
    sign_in_admin_on(study_admin, conn, "admin", ["study"])
    # Section admins edit partners, so they also upload and archive their documents.
    doc = upload(study_admin, "partner", partner["id"])
    assert doc.status_code == 200, doc.text
    archived = study_admin.post(f"/api/admin/partners/{partner['id']}/documents/{doc.json()['id']}/archive")
    assert archived.status_code == 200

    job_admin = new_client(api)
    sign_in_admin_on(job_admin, conn, "admin", ["job"])
    assert docs(job_admin, "partner", partner["id"]).json()["code"] == "FORBIDDEN"
    assert upload(job_admin, "partner", partner["id"]).json()["code"] == "FORBIDDEN"

    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert docs(finance, "partner", partner["id"]).json()["code"] == "FORBIDDEN"


def test_unlicensed_module(sa: TestClient, conn: Connection) -> None:
    partner = new_partner(sa, module="job", partner_type="employer")
    agent = new_agent(sa, sections=["job"])
    license_modules(conn, "course", "study")
    for kind, owner in (("partner", partner), ("agent", agent)):
        response = docs(sa, kind, owner["id"])
        assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"
        assert upload(sa, kind, owner["id"]).json()["code"] == "MODULE_NOT_LICENSED"


def test_unknown_and_other_owners(sa: TestClient) -> None:
    a1 = new_agent(sa)
    a2 = new_agent(sa)
    doc = upload(sa, "agent", a1["id"]).json()
    # A document is reached only through its own agent.
    assert sa.get(f"/api/admin/agents/{a2['id']}/documents/{doc['id']}/file").status_code == 404
    assert sa.post(f"/api/admin/agents/{a2['id']}/documents/{doc['id']}/archive").status_code == 404
    assert sa.get(f"/api/admin/partners/{a1['id']}/documents/{doc['id']}/file").status_code == 404
    assert docs(sa, "agent", str(uuid4())).status_code == 404
    assert docs(sa, "agent", "not-a-uuid").status_code == 404
    assert sa.get(f"/api/admin/agents/{a1['id']}/documents/not-a-uuid/file").status_code == 404


def test_database_keeps_documents(sa: TestClient, conn: Connection) -> None:
    agent = new_agent(sa)
    doc = upload(sa, "agent", agent["id"]).json()
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("UPDATE party_documents SET title = 'changed' WHERE id = :id"), {"id": doc["id"]})
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("DELETE FROM party_documents WHERE id = :id"), {"id": doc["id"]})
    sa.post(f"/api/admin/agents/{agent['id']}/documents/{doc['id']}/archive")
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(
                text("UPDATE party_documents SET status = 'active', archived_at = NULL, archived_by = NULL WHERE id = :id"),
                {"id": doc["id"]},
            )
