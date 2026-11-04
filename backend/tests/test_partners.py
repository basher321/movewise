"""B18: B2B partners with logos, shown only on their own module's page (b146-b152)."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from auth_helpers import audit_count, license_modules, sign_in_admin_on
from conftest import new_client

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32
PRIVATE = ("contact_name", "contact_email", "contact_phone", "agreement_ref", "agreement_until", "show_on_site", "active", "module")


def partner_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "module": "study",
        "partner_type": "university",
        "name": "Test Partner University",
        "country": "Canada",
        "website": "https://partner.example.test",
        "description": "Our partner for Canadian intakes.",
        "contact_name": "Private Person",
        "contact_email": "private@partner.example.test",
        "contact_phone": "+1 555 0100",
        "agreement_ref": "AGR-SECRET-1",
        "agreement_until": "2027-12-31",
        "show_on_site": True,
        "sort_order": 0,
        "active": True,
    }
    body.update(changes)
    return body


@pytest.fixture
def sa(client: TestClient, conn: Connection, act_as: Callable[..., Any]) -> TestClient:
    license_modules(conn, "course", "study", "job")
    act_as("super_admin")
    return client


def create(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/admin/partners", json=partner_body(**changes))
    assert response.status_code == 200, response.text
    return dict(response.json())


def upload(client: TestClient, partner_id: str, data: bytes = PNG, name: str = "logo.png", mime: str = "image/png") -> Any:
    return client.put(f"/api/admin/partners/{partner_id}/logo", files={"file": (name, data, mime)})


def public(client: TestClient, module: str) -> Any:
    return client.get("/api/partners", params={"module": module})


# b146
def test_b146_study_partner_only_on_study(api: FastAPI, sa: TestClient) -> None:
    partner = create(sa)
    with_logo = upload(sa, partner["id"])
    assert with_logo.status_code == 200, with_logo.text
    logo_url = with_logo.json()["logo_url"]
    assert logo_url and logo_url.startswith(f"/api/partners/{partner['id']}/logo?v=")
    anon = new_client(api)
    anon.cookies.clear()
    listed = public(anon, "study").json()
    assert [p["name"] for p in listed] == ["Test Partner University"] and listed[0]["logo_url"] == logo_url
    assert public(anon, "job").json() == [] and public(anon, "course").json() == []
    image = anon.get(logo_url)
    assert image.status_code == 200 and image.content == PNG and image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert anon.get(logo_url, headers={"If-None-Match": image.headers["etag"]}).status_code == 304
    create(sa, module="job", partner_type="employer", name="Gulf Builders")
    create(sa, module="course", partner_type="exam_board", name="Exam Board")
    assert [p["name"] for p in public(anon, "job").json()] == ["Gulf Builders"]
    assert [p["name"] for p in public(anon, "course").json()] == ["Exam Board"]
    assert public(anon, "other").json()["code"] == "VALIDATION"


def test_public_order(sa: TestClient) -> None:
    create(sa, name="Zeta", sort_order=0)
    create(sa, name="Alpha", sort_order=5)
    create(sa, name="Beta", sort_order=0)
    assert [p["name"] for p in public(sa, "study").json()] == ["Beta", "Zeta", "Alpha"]


# b147
def test_b147_hidden_or_off_is_not_public(api: FastAPI, sa: TestClient) -> None:
    hidden = create(sa, name="Hidden", show_on_site=False)
    off = create(sa, name="Off", active=False)
    for p in (hidden, off):
        assert upload(sa, p["id"]).status_code == 200
    anon = new_client(api)
    anon.cookies.clear()
    assert public(anon, "study").json() == []
    assert anon.get(f"/api/partners/{hidden['id']}/logo").status_code == 404
    assert anon.get(f"/api/partners/{off['id']}/logo").status_code == 404
    assert anon.get(f"/api/partners/{uuid4()}/logo").status_code == 404
    assert anon.get("/api/partners/not-a-uuid/logo").status_code == 404


# b148
def test_b148_unlicensed_module(api: FastAPI, sa: TestClient, conn: Connection) -> None:
    job = create(sa, module="job", partner_type="employer")
    upload(sa, job["id"])
    license_modules(conn, "course", "study")
    anon = new_client(api)
    anon.cookies.clear()
    response = public(anon, "job")
    assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"
    assert anon.get(f"/api/partners/{job['id']}/logo").status_code == 404
    assert sa.put(f"/api/admin/partners/{job['id']}", json=partner_body(module="job", partner_type="employer")).json()["code"] == "MODULE_NOT_LICENSED"
    assert all(p["module"] != "job" for p in sa.get("/api/admin/partners").json())


# b149
def test_b149_admin_own_sections_only(api: FastAPI, sa: TestClient, conn: Connection) -> None:
    study = create(sa)
    job = create(sa, module="job", partner_type="employer", name="Job Partner")
    admin = new_client(api)
    sign_in_admin_on(admin, conn, "admin", ["study"])
    assert [p["name"] for p in admin.get("/api/admin/partners").json()] == ["Test Partner University"]
    assert admin.post("/api/admin/partners", json=partner_body(name="By admin")).status_code == 200
    assert admin.post("/api/admin/partners", json=partner_body(module="job")).json()["code"] == "FORBIDDEN"
    assert admin.put(f"/api/admin/partners/{job['id']}", json=partner_body(module="job")).json()["code"] == "FORBIDDEN"
    assert upload(admin, job["id"]).json()["code"] == "FORBIDDEN"
    assert admin.post(f"/api/admin/partners/{job['id']}/logo/clear").json()["code"] == "FORBIDDEN"
    moved = admin.put(f"/api/admin/partners/{study['id']}", json=partner_body(module="job"))
    assert moved.json()["code"] == "FORBIDDEN"
    assert admin.get("/api/admin/partners", params={"module": "job"}).json()["code"] == "FORBIDDEN"
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.get("/api/admin/partners").json()["code"] == "FORBIDDEN"
    assert finance.post("/api/admin/partners", json=partner_body()).json()["code"] == "FORBIDDEN"
    anon = new_client(api)
    anon.cookies.clear()
    assert anon.get("/api/admin/partners").status_code == 401
    assert anon.post("/api/admin/partners", json=partner_body()).status_code == 401


# b150
def test_b150_logo_rules(sa: TestClient, conn: Connection) -> None:
    partner = create(sa)
    fake_png = upload(sa, partner["id"], b"<svg onload=alert(1)>", "logo.png", "image/png")
    assert fake_png.status_code == 422 and fake_png.json()["code"] == "VALIDATION"
    big = upload(sa, partner["id"], PNG + b"\x00" * (2 * 1024 * 1024))
    assert big.json()["code"] == "VALIDATION"
    assert sa.put(f"/api/admin/partners/{partner['id']}/logo", files={}).json()["code"] == "VALIDATION"
    first = upload(sa, partner["id"]).json()["logo_url"]
    second = upload(sa, partner["id"], WEBP, "logo.webp", "image/webp").json()["logo_url"]
    assert first != second
    assert conn.execute(text("SELECT count(*) FROM partner_logos")).scalar_one() >= 2
    cleared = sa.post(f"/api/admin/partners/{partner['id']}/logo/clear").json()
    assert cleared["logo_url"] is None
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("DELETE FROM partner_logos WHERE size_bytes > 0"))
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("DELETE FROM partners WHERE id = :id"), {"id": partner["id"]})


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"module": "other"},
        {"partner_type": "friend"},
        {"website": "http://insecure.example"},
        {"website": "javascript:alert(1)"},
        {"contact_email": "nope"},
        {"description": "x" * 301},
        {"agreement_until": "not a date"},
        {"show_on_site": "yes"},
        {"sort_order": 99999},
    ],
)
def test_partner_input_checked(sa: TestClient, conn: Connection, changes: dict[str, Any]) -> None:
    before = audit_count(conn)
    response = sa.post("/api/admin/partners", json=partner_body(**changes))
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION", response.text
    assert audit_count(conn) == before


# b151
def test_b151_no_private_fields_public(api: FastAPI, sa: TestClient) -> None:
    create(sa)
    anon = new_client(api)
    anon.cookies.clear()
    listed = public(anon, "study").json()
    assert listed and all(not (set(PRIVATE) & set(p)) for p in listed)
    raw = public(anon, "study").text
    assert "private@partner.example.test" not in raw and "AGR-SECRET-1" not in raw and "Private Person" not in raw


# b152
def test_b152_one_audit_row_per_change(sa: TestClient, conn: Connection) -> None:
    before = audit_count(conn)
    partner = create(sa)
    sa.put(f"/api/admin/partners/{partner['id']}", json=partner_body(name="Renamed"))
    upload(sa, partner["id"])
    sa.post(f"/api/admin/partners/{partner['id']}/logo/clear")
    assert audit_count(conn) == before + 4
    for action in ("partner.created", "partner.updated", "partner.logo_set", "partner.logo_cleared"):
        assert audit_count(conn, action) >= 1
    assert sa.put(f"/api/admin/partners/{uuid4()}", json=partner_body()).json()["code"] == "NOT_FOUND"
