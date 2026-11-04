"""b21, b22 and the applicant edge cases: sign-up with a username (no email code, owner decision
2026-11-01), sign-in, sessions per module, profile, staff password reset."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from auth_helpers import (
    PASSWORD,
    audit_count,
    license_modules,
    sign_in_admin_on,
    signin_applicant,
    signup_applicant,
    verified_applicant,
)
from conftest import new_client

# ---------- b21 ----------


def test_sign_up_with_username_signs_in_at_once(api: FastAPI, client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    signup = client.post(
        "/api/auth/applicant/study/signup",
        json={"name": "Nadia Rahman", "username": " Nadia.R ", "password": PASSWORD},
    )
    assert signup.status_code == 200, signup.text
    account = signup.json()
    assert account["id"].startswith("STU-")
    assert (account["username"], account["email"], account["phone"]) == ("nadia.r", None, "")
    assert "mw_app_study=" in signup.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json()["applicants"]["study"]["id"] == account["id"]
    # No email code is ever sent.
    assert conn.execute(text("SELECT count(*) FROM notifications")).scalar_one() == 0

    with new_client(api) as other:
        assert signin_applicant(other, "study", "NADIA.R").status_code == 200
        wrong = signin_applicant(other, "study", "nadia.r", "wrong password")
        assert wrong.json() == {"code": "UNAUTHENTICATED", "message": "Wrong username or password."}


def test_sign_in_with_email_works_when_one_was_given(api: FastAPI, client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    verified_applicant(client, conn, "study", "both.ways@example.test")
    with new_client(api) as other:
        assert signin_applicant(other, "study", "Both.Ways@Example.test").status_code == 200
        assert signin_applicant(other, "study", "both.ways").status_code == 200


def test_username_rules(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    empty = client.post("/api/auth/applicant/study/signup", json={"name": "A", "username": " ", "password": PASSWORD})
    assert empty.status_code == 422
    for bad in ("ab", "has space", "bad!", "x" * 31):
        response = signup_applicant(client, "study", "rules@example.test", username=bad)
        assert response.status_code == 422, bad
    assert signup_applicant(client, "study", "not-an-email", username="valid.name").status_code == 422
    taken = signup_applicant(client, "study", "first@example.test", username="same_name")
    assert taken.status_code == 200
    again = signup_applicant(client, "study", "second@example.test", username="SAME_NAME")
    assert again.json() == {"code": "CONFLICT", "message": "This username is taken. Please choose another one."}


def test_removed_code_endpoints(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    for path in ("send-code", "verify", "reset-request", "reset"):
        assert client.post(f"/api/auth/applicant/study/{path}", json={}).status_code in (404, 405)


def test_staff_reset_password(api: FastAPI, client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    account = verified_applicant(client, conn, "study", "forgot@example.test")
    account_id = conn.execute(text("SELECT id FROM applicant_accounts WHERE public_id = :p"), {"p": account["id"]}).scalar_one()
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    before = audit_count(conn)
    reset = staff.post(f"/api/admin/accounts/{account_id}/reset-password")
    assert reset.status_code == 200
    temporary = reset.json()["temporary_password"]
    assert len(temporary) == 10 and reset.json()["username"] == "forgot"
    assert audit_count(conn) == before + 1
    # Their old sessions end; the old password no longer works; the temporary one does.
    assert client.get("/api/auth/session").json()["applicants"] == {}
    assert signin_applicant(client, "study", "forgot").status_code == 401
    assert signin_applicant(client, "study", "forgot", temporary).status_code == 200
    assert temporary not in conn.execute(text("SELECT row_to_json(a)::text FROM applicant_accounts a")).scalars().all()[0]

    job_staff = new_client(api)
    sign_in_admin_on(job_staff, conn, "admin", ["job"])
    assert job_staff.post(f"/api/admin/accounts/{account_id}/reset-password").json()["code"] == "FORBIDDEN"
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert finance.post(f"/api/admin/accounts/{account_id}/reset-password").json()["code"] == "FORBIDDEN"


# ---------- b22 ----------


def test_one_email_in_two_modules_has_two_sessions(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    email = "both@example.test"
    study = verified_applicant(client, conn, "study", email)
    job = verified_applicant(client, conn, "job", email)
    assert job["id"].startswith("JOB-") and study["id"] != job["id"]

    applicants = client.get("/api/auth/session").json()["applicants"]
    assert set(applicants) == {"study", "job"}

    assert client.post("/api/auth/signout", json={"target": "study"}).status_code == 200
    applicants = client.get("/api/auth/session").json()["applicants"]
    assert set(applicants) == {"job"}
    modules = conn.execute(text("SELECT module FROM sessions WHERE kind = 'applicant'")).scalars().all()
    assert modules == ["job"]


# ---------- edge cases ----------


def test_sign_up_for_unlicensed_module(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    response = signup_applicant(client, "job", "someone@example.test")
    assert response.status_code == 403
    assert response.json()["code"] == "MODULE_NOT_LICENSED"


def test_same_email_and_module_twice_is_conflict(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    assert signup_applicant(client, "study", "twice@example.test").status_code == 200
    again = signup_applicant(client, "study", "  TWICE@Example.test ", username="another.name")
    assert again.status_code == 409
    assert again.json() == {
        "code": "CONFLICT",
        "message": "This email already has a Student Consultancy account. Please sign in.",
    }


def test_sign_out_without_session_does_nothing(client: TestClient, conn: Connection) -> None:
    before = conn.execute(text("SELECT count(*) FROM sessions")).scalar_one()
    response = client.post("/api/auth/signout", json={"target": "all"})
    assert response.status_code == 200
    assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == before


def test_stale_cookie_is_cleared(client: TestClient) -> None:
    client.cookies.set("mw_app_study", "A" * 43, domain="testserver.local", path="/api")
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.json()["applicants"] == {}
    cleared = response.headers.get("set-cookie", "")
    assert "mw_app_study=" in cleared and "Max-Age=0" in cleared


def test_unknown_module_is_refused(client: TestClient) -> None:
    assert signup_applicant(client, "other", "x@example.test").status_code == 422


# ---------- profile and password (F04) ----------


def test_profile_update(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    verified_applicant(client, conn, "study", "profile@example.test")
    bad = client.patch("/api/me/study/profile", json={"name": "New Name", "phone": "12345"})
    assert bad.status_code == 422
    good = client.patch(
        "/api/me/study/profile",
        json={"name": " New Name ", "phone": "+880 1712-345678", "country": "Bangladesh", "education": "BSc"},
    )
    assert good.status_code == 200
    body = good.json()
    assert (body["name"], body["phone"], body["country"], body["education"]) == (
        "New Name", "+8801712345678", "Bangladesh", "BSc",
    )
    # Email is optional: it can be removed and added again.
    removed = client.patch("/api/me/study/profile", json={"name": "New Name", "phone": "", "email": ""})
    assert removed.status_code == 200 and removed.json()["email"] is None
    added = client.patch("/api/me/study/profile", json={"name": "New Name", "phone": "", "email": "new@example.test"})
    assert added.json()["email"] == "new@example.test"


def test_profile_needs_that_modules_session(client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study", "job")
    verified_applicant(client, conn, "study", "only-study@example.test")
    response = client.patch("/api/me/job/profile", json={"name": "X", "phone": "01712345678"})
    assert response.status_code == 401


def test_change_password_ends_other_sessions(api: FastAPI, client: TestClient, conn: Connection) -> None:
    license_modules(conn, "study")
    email = "change@example.test"
    verified_applicant(client, conn, "study", email)
    with new_client(api) as other:
        assert signin_applicant(other, "study", email).status_code == 200

        wrong = client.post("/api/me/study/password", json={"current_password": "wrong one", "new_password": "newpass1"})
        assert wrong.status_code == 403
        right = client.post("/api/me/study/password", json={"current_password": PASSWORD, "new_password": "newpass1"})
        assert right.status_code == 200

        assert "study" in client.get("/api/auth/session").json()["applicants"]
        assert other.get("/api/auth/session").json()["applicants"] == {}
        assert signin_applicant(other, "study", email).status_code == 401
        assert signin_applicant(other, "study", email, "newpass1").status_code == 200
