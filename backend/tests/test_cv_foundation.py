"""B28 phase 1: CV Agent foundation - projects, auto-save, consent, encrypted uploads, clean-up."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.cv import cleanup, storage
from auth_helpers import audit_count, license_modules, verified_applicant
from conftest import new_client

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


@pytest.fixture
def me(client: TestClient, conn: Connection, temp_storage: Path) -> TestClient:
    license_modules(conn, "course", "study", "job", "visa", "remote")
    verified_applicant(client, conn, "study", "cv-person@example.test")
    return client


def new_project(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/me/study/cv/projects", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


def upload(client: TestClient, project_id: str, data: bytes, name: str = "cv.pdf", kind: str = "cv") -> Any:
    return client.post(
        f"/api/me/study/cv/projects/{project_id}/files",
        data={"doc_kind": kind},
        files={"file": (name, data, "application/octet-stream")},
    )


def consent(client: TestClient, project_id: str) -> None:
    assert client.post(f"/api/me/study/cv/projects/{project_id}/consent", json={"agree": True}).status_code == 200


def test_options_are_public(client: TestClient) -> None:
    options = client.get("/api/cv/options").json()
    assert len(options["cv_types"]) == 9 and len(options["categories"]) == 16
    assert len(options["featured_countries"]) == 18 and "Bangladesh" in options["countries"]
    assert options["max_files"] == 10 and options["max_file_mb"] == 10


def test_tables_keep_history(me: TestClient, conn: Connection) -> None:
    project = new_project(me)
    conn.execute(
        text("INSERT INTO cv_versions (project_id, version, data, reason) VALUES (:p, 1, '{}', 'answers')"),
        {"p": project["id"]},
    )
    for sql in (
        "DELETE FROM cv_projects WHERE id = :p",
        "UPDATE cv_versions SET reason = 'edited' WHERE project_id = :p",
        "DELETE FROM cv_versions WHERE project_id = :p",
    ):
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(text(sql), {"p": project["id"]})


def test_create_autosave_and_list(me: TestClient, conn: Connection) -> None:
    project = new_project(me, cv_type="overseas", cover_letter=True)
    assert project["step"] == 2 and project["status"] == "draft" and project["files"] == []
    pid = project["id"]
    saved = me.patch(f"/api/me/study/cv/projects/{pid}", json={
        "country": "Canada", "category": "it", "job_advert_text": "  Python developer  ", "doc_kinds": ["cv", "academic", "cv"],
        "page_length": 1, "step": 4, "title": "My   Canada CV"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["country"] == "Canada" and body["category"] == "it" and body["job_advert_text"] == "Python developer"
    assert body["doc_kinds"] == ["cv", "academic"] and body["page_length"] == 1 and body["step"] == 4
    assert body["title"] == "My Canada CV"
    assert audit_count(conn, "cv.saved") == 1 and audit_count(conn, "cv.created") == 1
    for bad in ({"country": "Atlantis"}, {"category": "pilot"}, {"page_length": 3}, {"step": 9}, {"cv_type": "poem"},
                {"doc_kinds": ["photo"]}, {"template": "fancy"}, {"title": "x" * 121}):
        assert me.patch(f"/api/me/study/cv/projects/{pid}", json=bad).status_code == 422, bad
    listed = me.get("/api/me/study/cv/projects").json()["items"]
    assert [p["id"] for p in listed] == [pid]


def test_only_the_owner(api: FastAPI, me: TestClient, conn: Connection) -> None:
    pid = new_project(me)["id"]
    other = new_client(api)
    other.cookies.clear()
    assert other.get(f"/api/me/study/cv/projects/{pid}").status_code == 401
    verified_applicant(other, conn, "study", "someone-else@example.test")
    assert other.get(f"/api/me/study/cv/projects/{pid}").status_code == 404
    assert other.patch(f"/api/me/study/cv/projects/{pid}", json={"step": 3}).status_code == 404
    assert me.get(f"/api/me/job/cv/projects/{pid}").status_code == 401
    license_modules(conn, "course")
    assert me.get("/api/me/study/cv/projects").json()["code"] == "MODULE_NOT_LICENSED"


def test_upload_needs_consent_and_is_encrypted(me: TestClient, conn: Connection, temp_storage: Path) -> None:
    pid = new_project(me)["id"]
    assert upload(me, pid, PDF).status_code == 409
    assert me.post(f"/api/me/study/cv/projects/{pid}/consent", json={"agree": False}).status_code == 422
    consent(me, pid)
    response = upload(me, pid, PDF, "My CV.pdf")
    assert response.status_code == 200, response.text
    item = response.json()["files"][0]
    assert item["file_name"] == "My CV.pdf" and item["mime"] == "application/pdf" and item["extraction_status"] == "waiting"
    stored = conn.execute(text("SELECT storage_path, delete_after - created_at AS keep FROM cv_files")).one()
    on_disk = (temp_storage / stored.storage_path).read_bytes()
    assert PDF not in on_disk and storage.read(stored.storage_path) == PDF
    assert stored.keep.days == 30
    assert audit_count(conn, "cv.file_uploaded") == 1


def test_upload_types_and_limits(me: TestClient, conn: Connection) -> None:
    pid = new_project(me)["id"]
    consent(me, pid)
    assert upload(me, pid, b"hello", "notes.txt").status_code == 422
    assert upload(me, pid, PDF, kind="selfie").status_code == 422
    assert upload(me, pid, b"%PDF-" + b"0" * (10 * 1024 * 1024)).status_code in (413, 422)
    docx = next(f for f in upload(me, pid, docx_bytes(), "cv.docx").json()["files"] if f["file_name"] == "cv.docx")
    assert docx["mime"].endswith("wordprocessingml.document") and docx["extraction_status"] == "waiting"
    doc = next(f for f in upload(me, pid, DOC, "old.doc").json()["files"] if f["file_name"] == "old.doc")
    assert doc["mime"] == "application/msword" and doc["extraction_status"] == "unsupported"
    assert upload(me, pid, PNG, "letter.png", "experience").status_code == 200
    for n in range(7):
        assert upload(me, pid, PDF, f"f{n}.pdf").status_code == 200
    assert upload(me, pid, PDF, "eleven.pdf").status_code == 422


def test_remove_file_duplicate_and_delete(me: TestClient, conn: Connection) -> None:
    project = new_project(me, cv_type="student")
    pid = project["id"]
    consent(me, pid)
    fid = upload(me, pid, PDF).json()["files"][0]["id"]
    removed = me.post(f"/api/me/study/cv/projects/{pid}/files/{fid}/remove").json()["files"][0]
    assert removed["removed"] is True
    assert conn.execute(text("SELECT storage_path FROM cv_files WHERE id = :id"), {"id": fid}).scalar_one() is None
    copy = me.post(f"/api/me/study/cv/projects/{pid}/duplicate").json()
    assert copy["id"] != pid and copy["cv_type"] == "student" and copy["files"] == []
    deleted = me.post(f"/api/me/study/cv/projects/{pid}/delete")
    assert deleted.status_code == 200 and deleted.json()["status"] == "deleted"
    assert me.get(f"/api/me/study/cv/projects/{pid}").status_code == 404
    assert [p["id"] for p in me.get("/api/me/study/cv/projects").json()["items"]] == [copy["id"]]
    assert audit_count(conn, "cv.deleted") == 1


def test_expired_files_are_cleared(me: TestClient, conn: Connection) -> None:
    pid = new_project(me)["id"]
    consent(me, pid)
    upload(me, pid, PDF)
    upload(me, pid, PNG, "b.png")
    conn.execute(text("UPDATE cv_files SET delete_after = now() - interval '1 minute' WHERE file_name = 'cv.pdf'"))
    assert cleanup.remove_expired(conn) == 1
    rows = conn.execute(text("SELECT file_name, deleted_at IS NOT NULL AS gone FROM cv_files ORDER BY file_name")).all()
    assert [(r.file_name, r.gone) for r in rows] == [("b.png", False), ("cv.pdf", True)]
    assert cleanup.remove_expired(conn) == 0
    assert audit_count(conn, "cv.files_expired") == 1


def test_detect_mime() -> None:
    assert storage.detect_mime(PDF) == storage.PDF
    assert storage.detect_mime(docx_bytes()) == storage.DOCX
    assert storage.detect_mime(b"PK\x03\x04broken") is None
    assert storage.detect_mime(b"GIF89a") is None
