"""b124-b131: "Forgot password?" by email link, and the Super Admin reset in the Team tab (B15)."""

import re
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import PASSWORD, TEST_ADMIN_PASSWORD, license_modules, sign_in_admin_on, signin_applicant, signup_applicant
from conftest import insert_admin, new_client
from test_notify import set_up_email

NEW_PASSWORD = "fresh pass 1"
LINK_EVENT = "password_reset_link"


def _forgot(client: TestClient, kind: str, login: str) -> Any:
    return client.post("/api/auth/password/forgot", json={"kind": kind, "login": login})


def _reset(client: TestClient, token: str, password: str = NEW_PASSWORD) -> Any:
    return client.post("/api/auth/password/reset", json={"token": token, "new_password": password})


def _emails(conn: Connection) -> list[Any]:
    return list(
        conn.execute(
            text("SELECT to_address, body FROM notifications WHERE event = :e ORDER BY created_at"), {"e": LINK_EVENT}
        ).mappings()
    )


def _token(conn: Connection) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", _emails(conn)[-1]["body"])
    assert match is not None
    return match.group(1)


def _count(conn: Connection, sql: str, **params: Any) -> int:
    return int(conn.execute(text(sql), params).scalar_one())


def _admin_signin(client: TestClient, email: str, password: str) -> Any:
    return client.post("/api/auth/admin/signin", json={"email": email, "password": password})


# ---------- b124 ----------


def test_email_not_set_up(client: TestClient, conn: Connection) -> None:
    _, email = insert_admin(conn, "admin")
    assert client.get("/api/auth/password/options").json() == {"email": False}
    response = _forgot(client, "admin", email)
    assert response.status_code == 409
    assert response.json() == {"code": "CONFLICT", "message": "Email is not set up, so a reset link cannot be sent."}
    assert _emails(conn) == []


# ---------- b125 ----------


def test_staff_link_is_emailed_and_unknown_email_looks_the_same(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "super_admin")
    assert client.get("/api/auth/password/options").json() == {"email": True}

    known = _forgot(client, "admin", email.upper())
    unknown = _forgot(client, "admin", "nobody@example.test")
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"ok": True}

    emails = _emails(conn)
    assert len(emails) == 1 and emails[0]["to_address"] == email
    assert "/reset-password?token=" in emails[0]["body"]
    assert _count(conn, "SELECT count(*) FROM password_resets") == 1
    assert _count(conn, "SELECT count(*) FROM audit_log WHERE action = 'password.reset_requested'") == 1


def test_pending_or_deactivated_staff_get_nothing(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    admin_id, email = insert_admin(conn, "admin")
    conn.execute(text("UPDATE admin_users SET active = false WHERE id = :id"), {"id": admin_id})
    assert _forgot(client, "admin", email).json() == {"ok": True}
    assert _emails(conn) == []


# ---------- b126 ----------


def test_link_resets_once(client: TestClient, conn: Connection, api: FastAPI) -> None:
    set_up_email(conn)
    admin_id, email = sign_in_admin_on(client, conn, "admin")
    assert client.get("/api/auth/session").json()["admin"] is not None
    _forgot(new_client(api), "admin", email)
    token = _token(conn)

    browser = new_client(api)
    done = _reset(browser, token)
    assert done.status_code == 200
    assert done.json() == {"ok": True, "kind": "admin"}
    assert client.get("/api/auth/session").json()["admin"] is None
    assert _admin_signin(browser, email, TEST_ADMIN_PASSWORD).status_code == 401
    assert _admin_signin(browser, email, NEW_PASSWORD).status_code == 200
    assert _count(conn, "SELECT count(*) FROM audit_log WHERE action = 'password.reset_by_link'") == 1

    again = _reset(browser, token, "another pass")
    assert again.status_code == 410
    assert again.json() == {"code": "EXPIRED", "message": "This reset link has expired. Please ask for a new one."}


def test_old_and_wrong_links(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "finance")
    _forgot(client, "admin", email)
    token = _token(conn)
    conn.execute(text("UPDATE password_resets SET expires_at = now() - interval '1 minute'"))
    assert _reset(client, token).json()["code"] == "EXPIRED"
    wrong = _reset(client, "not-a-real-token")
    assert wrong.status_code == 422
    assert wrong.json() == {"code": "VALIDATION", "message": "This reset link is not valid."}


def test_short_new_password_is_refused_and_link_still_works(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "admin")
    _forgot(client, "admin", email)
    token = _token(conn)
    assert _reset(client, token, "12345").json()["code"] == "VALIDATION"
    assert _reset(client, token).status_code == 200


def test_a_new_link_does_not_leave_older_ones_usable(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "admin")
    _forgot(client, "admin", email)
    first = _token(conn)
    _forgot(client, "admin", email)
    second = _token(conn)
    assert _reset(client, second).status_code == 200
    assert _reset(client, first).json()["code"] == "EXPIRED"


# ---------- b127 ----------


def test_applicant_by_username_or_email(client: TestClient, conn: Connection, api: FastAPI) -> None:
    set_up_email(conn)
    license_modules(conn, "study")
    signup_applicant(client, "study", "learner@example.test", username="learner1")
    assert _forgot(new_client(api), "study", "LEARNER1").json() == {"ok": True}
    assert _forgot(new_client(api), "study", "learner@example.test").json() == {"ok": True}
    assert len(_emails(conn)) == 2

    browser = new_client(api)
    assert _reset(browser, _token(conn)).json() == {"ok": True, "kind": "study"}
    assert signin_applicant(browser, "study", "learner1", PASSWORD).status_code == 401
    assert signin_applicant(browser, "study", "learner1", NEW_PASSWORD).status_code == 200


def test_applicant_without_email_gets_nothing(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    license_modules(conn, "job")
    response = client.post(
        "/api/auth/applicant/job/signup",
        json={"name": "No Mail", "username": "nomail1", "email": "", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert _forgot(client, "job", "nomail1").json() == {"ok": True}
    assert _emails(conn) == []


def test_unlicensed_module(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    license_modules(conn, "study")
    assert _forgot(client, "course", "anyone").json()["code"] == "MODULE_NOT_LICENSED"


# ---------- b128 ----------


def test_limits(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "admin")
    for _ in range(4):
        assert _forgot(client, "admin", email).json() == {"ok": True}
    assert len(_emails(conn)) == 3

    for i in range(17):
        _, other = insert_admin(conn, "admin")
        assert _forgot(client, "admin", other).status_code == 200, i
    _, last = insert_admin(conn, "admin")
    blocked = _forgot(client, "admin", last)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_TRIES"


# ---------- b129 ----------


def test_notifications_list_masks_the_token(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "admin")
    _forgot(client, "admin", email)
    token = _token(conn)
    sign_in_admin_on(client, conn, "super_admin")
    items = client.get("/api/admin/notifications").json()["items"]
    listed = next(i for i in items if i["event"] == LINK_EVENT)
    assert token not in listed["body"]
    assert "token=••••••" in listed["body"]


# ---------- b130 ----------


def test_team_reset(client: TestClient, conn: Connection, api: FastAPI) -> None:
    me_id, _ = sign_in_admin_on(client, conn, "super_admin")
    for role in ("admin", "super_admin"):
        other_id, other_email = insert_admin(conn, role)
        their = new_client(api)
        assert _admin_signin(their, other_email, TEST_ADMIN_PASSWORD).status_code == 200

        response = client.post(f"/api/admin/team/{other_id}/reset-password")
        assert response.status_code == 200
        temporary = response.json()["temporary_password"]
        assert len(temporary) == 10
        assert their.get("/api/auth/session").json()["admin"] is None
        assert _admin_signin(their, other_email, TEST_ADMIN_PASSWORD).status_code == 401
        assert _admin_signin(their, other_email, temporary).status_code == 200
    assert _count(conn, "SELECT count(*) FROM audit_log WHERE action = 'team.password_reset'") == 2

    own = client.post(f"/api/admin/team/{me_id}/reset-password")
    assert own.status_code == 403
    assert own.json() == {"code": "FORBIDDEN", "message": "Use My account to change your own password."}
    assert client.post("/api/admin/team/not-a-uuid/reset-password").status_code == 404


def test_team_reset_needs_super_admin(client: TestClient, conn: Connection) -> None:
    sign_in_admin_on(client, conn, "admin")
    other_id, _ = insert_admin(conn, "finance")
    assert client.post(f"/api/admin/team/{other_id}/reset-password").json()["code"] == "FORBIDDEN"


# ---------- b131 ----------


def test_no_token_or_password_leaks(client: TestClient, conn: Connection) -> None:
    set_up_email(conn)
    _, email = insert_admin(conn, "admin")
    forgot = _forgot(client, "admin", email)
    token = _token(conn)
    reset = _reset(client, token)
    for response in (forgot, reset):
        assert token not in response.text and NEW_PASSWORD not in response.text and "password_hash" not in response.text
    details = " ".join(r for (r,) in conn.execute(text("SELECT detail FROM audit_log")).all())
    assert token not in details and NEW_PASSWORD not in details
    stored = conn.execute(text("SELECT token_hash FROM password_resets")).scalar_one()
    assert token.encode() not in bytes(stored)
