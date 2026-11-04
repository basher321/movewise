"""B06: documents - upload, storage, viewing, review and expiry (b58-b70)."""

import hashlib
import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.files import clean_name
from app.licence import today_dhaka
from app.routers import documents as documents_router
from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import university_body, vacancy_body

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PASSPORT = "Valid passport"


@pytest.fixture
def study(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> dict[str, Any]:
    """A super admin (act_as) and an applicant with an active study application, on one client."""
    license_modules(conn, "course", "study", "job")
    act_as("super_admin")
    uni = client.post("/api/admin/universities", json=university_body()).json()
    verified_applicant(client, conn, "study", "docs@example.test")
    app = client.post("/api/me/study/applications", json={"item_slug": uni["slug"], "answers": {}}).json()
    return dict(app)


def upload(client: TestClient, app_id: str, data: bytes = PDF, name: str = "passport.pdf", doc_type: str = PASSPORT) -> Any:
    return client.post(
        f"/api/me/study/applications/{app_id}/documents",
        data={"type": doc_type},
        files={"file": (name, data, "application/pdf")},
    )


def stored_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


# b58
def test_b58_documents_cannot_be_deleted(client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    assert upload(client, study["id"]).status_code == 200
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("DELETE FROM documents WHERE application_id = :id"), {"id": study["id"]})


# b59
def test_b59_upload_pdf(client: TestClient, conn: Connection, study: dict[str, Any], temp_storage: Path) -> None:
    response = upload(client, study["id"], name="../../etc/My Passport.pdf")
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["original_name"] == "My Passport.pdf"
    assert doc["mime"] == "application/pdf" and doc["status"] == "pending"
    row = conn.execute(text("SELECT * FROM documents WHERE id = :id"), {"id": doc["id"]}).mappings().one()
    assert row["size_bytes"] == len(PDF)
    assert row["sha256"] == hashlib.sha256(PDF).hexdigest()
    on_disk = temp_storage / row["stored_name"]
    assert on_disk.read_bytes() == PDF
    assert re.fullmatch(r"[0-9a-f]{32}", on_disk.name) and on_disk.suffix == ""


def test_clean_name() -> None:
    assert clean_name("C:\\Users\\x\\My\x00\x07 Passport.pdf") == "My Passport.pdf"
    assert clean_name("") == "document"
    assert len(clean_name("a" * 500)) == 200


# b60
@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"<html><script>alert(1)</script></html>", "fake.pdf"),
        (b"MZ\x90\x00" + b"\x00" * 100, "tool.exe"),
        (b"", "empty.pdf"),
        (b"%PDF-" + b"0" * int(2.1 * 1024 * 1024), "big.pdf"),
    ],
    ids=["html-as-pdf", "exe", "empty", "2.1MB"],
)
def test_b60_bad_files(client: TestClient, study: dict[str, Any], data: bytes, name: str) -> None:
    response = upload(client, study["id"], data=data, name=name)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"


def test_unknown_type_and_png(client: TestClient, study: dict[str, Any]) -> None:
    assert upload(client, study["id"], doc_type="Birth certificate").status_code == 422
    png = upload(client, study["id"], data=PNG, name="photo.png", doc_type="CV")
    assert png.json()["mime"] == "image/png"


# b61
def test_b61_replace(client: TestClient, conn: Connection, study: dict[str, Any], temp_storage: Path) -> None:
    first = upload(client, study["id"]).json()
    second = upload(client, study["id"]).json()
    statuses = dict(conn.execute(text("SELECT id::text, status FROM documents")).all())
    assert statuses == {first["id"]: "replaced", second["id"]: "pending"}
    assert len(stored_files(temp_storage)) >= 2
    detail = client.get(f"/api/me/study/applications/{study['id']}").json()
    assert [d["id"] for d in detail["documents"]] == [second["id"]]
    # Staff can still open the replaced one.
    assert client.get(f"/api/admin/documents/{first['id']}/file").status_code == 200


# b62
def test_b62_who_may_open(api: FastAPI, client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    doc = upload(client, study["id"]).json()
    other = new_client(api)
    verified_applicant(other, conn, "study", "someone@example.test")
    assert other.get(doc["file_url"]).status_code == 404
    job_staff = new_client(api)
    sign_in_admin_on(job_staff, conn, "admin", ["job"])
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    for staff in (job_staff, finance):
        response = staff.get(f"/api/admin/documents/{doc['id']}/file")
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    # The job-only admin may list documents, but sees none of the study ones.
    assert job_staff.get("/api/admin/documents?filter=all").json()["total"] == 0
    assert finance.get("/api/admin/documents").status_code == 403


# b63
def test_b63_file_headers_and_view_audit(client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    doc = upload(client, study["id"]).json()
    mine = client.get(doc["file_url"])
    assert mine.content == PDF
    assert audit_count(conn, "Document viewed") == 0
    response = client.get(f"/api/admin/documents/{doc['id']}/file")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"].startswith('inline; filename="passport.pdf"')
    assert audit_count(conn, "Document viewed") == 1


def test_missing_file_is_internal(client: TestClient, conn: Connection, study: dict[str, Any], temp_storage: Path) -> None:
    doc = upload(client, study["id"]).json()
    stored = conn.execute(text("SELECT stored_name FROM documents WHERE id = :id"), {"id": doc["id"]}).scalar_one()
    (temp_storage / stored).unlink()
    response = client.get(f"/api/admin/documents/{doc['id']}/file")
    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL", "message": "File is missing"}


def verify(client: TestClient, doc_id: str, expiry: str | None) -> Any:
    return client.post(f"/api/admin/documents/{doc_id}/verify", json={"expiry": expiry})


# b64
def test_b64_expiry(client: TestClient, study: dict[str, Any]) -> None:
    today = today_dhaka()
    soon = upload(client, study["id"]).json()
    assert verify(client, soon["id"], (today + timedelta(days=30)).isoformat()).json()["shown_status"] == "expiring"
    old = upload(client, study["id"], doc_type="CV").json()
    assert verify(client, old["id"], (today - timedelta(days=1)).isoformat()).json()["shown_status"] == "expired"
    bad = upload(client, study["id"], doc_type="Proof of funds").json()
    client.post(f"/api/admin/documents/{bad['id']}/reject", json={"reason": "Blurry"})
    assert verify(client, bad["id"], None).status_code == 409
    assert verify(client, soon["id"], None).status_code == 409
    assert client.post(f"/api/admin/documents/{bad['id']}/verify", json={"expiry": "2030-02-30"}).status_code == 422


# b65
def test_b65_reject(client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    doc = upload(client, study["id"]).json()
    url = f"/api/admin/documents/{doc['id']}/reject"
    assert client.post(url, json={"reason": " "}).status_code == 422
    assert client.post(url, json={"reason": "x" * 501}).status_code == 422
    done = client.post(url, json={"reason": "The photo page is cut off"})
    assert done.json()["shown_status"] == "rejected"
    history = client.get(f"/api/me/study/applications/{study['id']}").json()["history"]
    assert history[0]["text"] == f"{PASSPORT} rejected"
    assert history[0]["note"] == "The photo page is cut off"
    subject = conn.execute(text("SELECT subject FROM notifications WHERE event = 'document_rejected'")).scalar_one()
    assert subject == f"Please upload your {PASSPORT} again"


# b66
def test_b66_no_upload_when_withdrawn(client: TestClient, study: dict[str, Any]) -> None:
    doc = upload(client, study["id"]).json()
    client.post(f"/api/me/study/applications/{study['id']}/withdraw")
    response = upload(client, study["id"])
    assert response.status_code == 409
    assert client.get(doc["file_url"]).status_code == 200


# b67
def test_b67_failed_insert_leaves_no_file(
    client: TestClient, study: dict[str, Any], temp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = len(stored_files(temp_storage))

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("forced database failure")

    monkeypatch.setattr(documents_router, "add_event", fail)
    response = upload(client, study["id"])
    assert response.status_code == 500
    assert len(stored_files(temp_storage)) == before


# b68
def test_b68_expiring_filter(client: TestClient, study: dict[str, Any]) -> None:
    today = today_dhaka()
    soon = upload(client, study["id"]).json()
    verify(client, soon["id"], (today + timedelta(days=30)).isoformat())
    later = upload(client, study["id"], doc_type="CV").json()
    verify(client, later["id"], (today + timedelta(days=200)).isoformat())
    upload(client, study["id"], doc_type="Proof of funds")
    listed = client.get("/api/admin/documents?filter=expiring").json()
    assert [d["id"] for d in listed["items"]] == [soon["id"]]
    assert listed["items"][0]["application_ref"] == study["ref"]
    assert client.get("/api/admin/documents?filter=pending").json()["total"] == 1
    assert client.get("/api/admin/documents?filter=all").json()["total"] == 3
    assert client.get("/api/admin/documents?filter=nope").status_code == 422


# b69
def test_b69_missing_count(client: TestClient, study: dict[str, Any]) -> None:
    detail = client.get(f"/api/me/study/applications/{study['id']}").json()
    required = detail["required_types"]
    assert detail["missing_count"] == len(required) == 7
    for done, doc_type in enumerate(required, start=1):
        upload(client, study["id"], doc_type=doc_type)
        detail = client.get(f"/api/me/study/applications/{study['id']}").json()
        assert detail["missing_count"] == len(required) - done
    admin_view = client.get(f"/api/admin/applications/{study['id']}").json()
    assert admin_view["missing_count"] == 0
    assert admin_view["documents"][0]["file_url"].startswith("/api/admin/documents/")


# b70
def test_b70_one_audit_row_per_change(client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    before = audit_count(conn)
    first = upload(client, study["id"]).json()
    assert audit_count(conn) == before + 1
    verify(client, first["id"], None)
    assert audit_count(conn) == before + 2
    second = upload(client, study["id"], doc_type="CV").json()
    client.post(f"/api/admin/documents/{second['id']}/reject", json={"reason": "Old"})
    assert audit_count(conn) == before + 4


def test_upload_rate_limit(client: TestClient, conn: Connection, study: dict[str, Any]) -> None:
    for _ in range(20):
        assert upload(client, study["id"]).status_code == 200
    response = upload(client, study["id"])
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_TRIES"
