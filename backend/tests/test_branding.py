"""b13 and b17 (pictures): logo and home picture upload, serving and clearing."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 200
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'


def _audit_count(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one())


def _detail_count(conn: Connection, detail: str) -> int:
    query = text("SELECT count(*) FROM audit_log WHERE detail = :detail")
    return int(conn.execute(query, {"detail": detail}).scalar_one())


def _upload(client: TestClient, kind: str, name: str, data: bytes, mime: str) -> Any:
    return client.put(f"/api/settings/{kind}", files={"file": (name, data, mime)})


def test_png_logo_upload_and_serve(client: TestClient, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    response = _upload(client, "logo", "logo.png", PNG, "image/png")
    assert response.status_code == 200
    assert response.json()["logo_url"].startswith("/api/branding/logo?v=")

    image = client.get("/api/branding/logo")
    assert image.status_code == 200
    assert image.content == PNG
    assert image.headers["content-type"] == "image/png"
    etag = image.headers["etag"]
    assert client.get("/api/branding/logo", headers={"If-None-Match": etag}).status_code == 304
    assert client.get("/api/settings/public").json()["logo_url"] is not None


def test_jpeg_and_webp_are_accepted(client: TestClient, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    assert _upload(client, "hero", "a.jpg", JPEG, "image/jpeg").status_code == 200
    assert client.get("/api/branding/hero").headers["content-type"] == "image/jpeg"
    assert _upload(client, "hero", "a.webp", WEBP, "image/webp").status_code == 200
    assert client.get("/api/branding/hero").headers["content-type"] == "image/webp"


def test_svg_large_and_fake_png_are_refused(client: TestClient, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    too_large = b"\x89PNG\r\n\x1a\n" + b"\x00" * (600 * 1024)
    for name, data, mime in [
        ("logo.svg", SVG, "image/svg+xml"),
        ("big.png", too_large, "image/png"),
        ("text.png", b"just some text, not a picture", "image/png"),
    ]:
        response = _upload(client, "logo", name, data, mime)
        assert response.status_code == 422, name
        assert response.json()["code"] == "VALIDATION"


def test_hero_limit_is_1_5_mb(client: TestClient, act_as: Callable[..., Any]) -> None:
    act_as("super_admin")
    under = b"\x89PNG\r\n\x1a\n" + b"\x00" * (1536 * 1024 - 8)
    assert _upload(client, "hero", "ok.png", under, "image/png").status_code == 200
    assert _upload(client, "hero", "big.png", under + b"\x00", "image/png").status_code == 422


def test_no_picture_is_not_found(client: TestClient) -> None:
    response = client.get("/api/branding/hero")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_clear_goes_back_to_default_and_keeps_the_old_row(
    client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    act_as("super_admin")
    assert _upload(client, "logo", "logo.png", PNG, "image/png").status_code == 200
    response = client.post("/api/settings/logo/clear")
    assert response.status_code == 200
    assert response.json()["logo_url"] is None
    assert client.get("/api/branding/logo").status_code == 404
    kept = conn.execute(
        text("SELECT count(*) FROM branding_images WHERE kind = 'logo' AND bytes = :data"), {"data": PNG}
    ).scalar_one()
    assert kept == 1


def test_upload_needs_super_admin(client: TestClient, act_as: Callable[..., Any]) -> None:
    assert _upload(client, "logo", "logo.png", PNG, "image/png").status_code == 401
    act_as("admin")
    assert _upload(client, "logo", "logo.png", PNG, "image/png").status_code == 403
    assert client.post("/api/settings/logo/clear").status_code == 403


def test_each_picture_change_writes_one_audit_row(
    client: TestClient, conn: Connection, act_as: Callable[..., Any]
) -> None:
    act_as("super_admin")
    steps = [
        (lambda: _upload(client, "logo", "logo.png", PNG, "image/png"), "Logo changed"),
        (lambda: client.post("/api/settings/logo/clear"), "Logo changed (default)"),
        (lambda: _upload(client, "hero", "hero.png", PNG, "image/png"), "Home picture changed"),
        (lambda: client.post("/api/settings/hero/clear"), "Home picture changed (default)"),
    ]
    for step, detail in steps:
        before = _audit_count(conn)
        same = _detail_count(conn, detail)
        assert step().status_code == 200
        assert _audit_count(conn) == before + 1
        assert _detail_count(conn, detail) == same + 1
