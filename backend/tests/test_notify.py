"""B08: sending notifications by SMTP and WhatsApp, retries and the delivery log (b86-b96).

No real mail server or Meta is contacted: SMTP_FACTORY and the WhatsApp transport are fakes.
The worker's steps run inside the test transaction (savepoints), so nothing is committed.
"""

import json
import logging
import re
import smtplib
import socket
from collections.abc import Callable
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, TypeVar

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.notify import email_smtp, whatsapp
from app.notify.outbox import queue_message
from app.notify.worker import process_once
from app.secrets_store import save_secret
from auth_helpers import audit_count, sign_in_admin_on
from conftest import BACKEND_DIR, new_client

SMTP_PASSWORD = "smtp-pass-SECRET-4411"
WA_TOKEN = "EAAG-wa-token-SECRET-9090"
T = TypeVar("T")


class FakeSMTP:
    sent: list[EmailMessage] = []
    error: BaseException | None = None
    logins: list[tuple[str, str]] = []

    def __init__(self, config: Any) -> None:
        if FakeSMTP.error is not None:
            raise FakeSMTP.error

    def login(self, user: str, password: str) -> None:
        FakeSMTP.logins.append((user, password))

    def send_message(self, message: EmailMessage) -> dict[str, Any]:
        FakeSMTP.sent.append(message)
        return {}

    def quit(self) -> None:
        pass


class FakeMeta:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": f"token {WA_TOKEN} rejected", "code": 190}})
        return httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.TEST1"}]})


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.sent, FakeSMTP.error, FakeSMTP.logins = [], None, []
    monkeypatch.setattr(email_smtp, "SMTP_FACTORY", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def meta(monkeypatch: pytest.MonkeyPatch) -> FakeMeta:
    fake = FakeMeta()
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(fake.handle))
    return fake


@pytest.fixture
def run(conn: Connection) -> Callable[[Callable[[Connection], T]], T]:
    def step(fn: Callable[[Connection], T]) -> T:
        with conn.begin_nested():
            return fn(conn)

    return step


def set_up_email(conn: Connection) -> None:
    conn.execute(
        text(
            "UPDATE settings SET name = 'Test Agency', address = 'House 1, Dhaka 1207', email = 'office@agency.test', "
            "smtp_host = 'smtp.agency.test', smtp_username = 'mailer', mail_sender_name = 'Test Agency', "
            "mail_sender_email = 'noreply@agency.test' WHERE singleton = 'settings'"
        )
    )
    save_secret(conn, "mail.smtp_password", SMTP_PASSWORD)


def set_up_whatsapp(conn: Connection) -> None:
    conn.execute(
        text(
            "UPDATE settings SET whatsapp_phone_number_id = '1234567890', whatsapp_template_name = 'agency_update', "
            "whatsapp_template_language = 'en_US' WHERE singleton = 'settings'"
        )
    )
    save_secret(conn, "whatsapp.token", WA_TOKEN)


def row(conn: Connection, channel: str = "email") -> Any:
    return conn.execute(
        text("SELECT *, next_attempt_at - now() AS wait FROM notifications WHERE channel = :c ORDER BY at DESC LIMIT 1"),
        {"c": channel},
    ).mappings().one()


def make_due(conn: Connection) -> None:
    conn.execute(text("UPDATE notifications SET next_attempt_at = now() - interval '1 second' WHERE status = 'queued'"))


# b86
def test_b86_columns_added_rows_kept(conn: Connection) -> None:
    queue_message(conn, "A", "a@example.test", None, None, "x", "Subject", "Body")
    r = row(conn)
    assert (r["status"], r["tries"], r["last_error"], r["sending_since"], r["sent_at"]) == ("queued", 0, "", None, None)


# b87
def test_b87_email_not_set_up(conn: Connection, run: Any, smtp: type[FakeSMTP]) -> None:
    queue_message(conn, "A", "a@example.test", None, None, "x", "Subject", "Body")
    assert process_once(run) == 1
    r = row(conn)
    assert (r["status"], r["last_error"], r["tries"]) == ("queued", "Email is not set up", 0)
    assert smtp.sent == []


# b88
def test_b88_email_sent(conn: Connection, run: Any, smtp: type[FakeSMTP]) -> None:
    set_up_email(conn)
    queue_message(conn, "Rahim", "rahim@example.test", None, "study", "x", "Your update", "Hello <b>Rahim</b> & co\n\nBye")
    process_once(run)
    r = row(conn)
    assert r["status"] == "sent" and r["sent_at"] is not None and r["tries"] == 1
    message = smtp.sent[0]
    assert message["From"] == "Test Agency <noreply@agency.test>"
    assert message["Reply-To"] == "office@agency.test"
    assert message["Subject"] == "Your update"
    assert smtp.logins == [("mailer", SMTP_PASSWORD)]
    plain = message.get_body(("plain",))
    html_part = message.get_body(("html",))
    assert plain is not None and "Hello <b>Rahim</b> & co" in plain.get_content()
    assert html_part is not None
    html = html_part.get_content()
    assert "Hello &lt;b&gt;Rahim&lt;/b&gt; &amp; co" in html and "<b>Rahim</b>" not in html
    assert "Test Agency" in html and "Dhaka 1207" in html


# b89
def test_b89_retries_then_failed(conn: Connection, run: Any, smtp: type[FakeSMTP]) -> None:
    set_up_email(conn)
    queue_message(conn, "A", "a@example.test", None, None, "x", "S", "B")
    smtp.error = socket.timeout("timed out")
    for tries, minutes in ((1, 1), (2, 5), (3, 30)):
        process_once(run)
        r = row(conn)
        assert (r["status"], r["tries"]) == ("queued", tries)
        assert r["wait"] == timedelta(minutes=minutes)
        make_due(conn)
    process_once(run)
    assert (row(conn)["status"], row(conn)["tries"]) == ("failed", 4)

    queue_message(conn, "B", "b@example.test", None, None, "y", "S", "B")
    smtp.error = smtplib.SMTPResponseException(550, b"mailbox unavailable")
    process_once(run)
    r = conn.execute(text("SELECT * FROM notifications WHERE to_address = 'b@example.test'")).mappings().one()
    assert (r["status"], r["tries"], r["last_error"]) == ("failed", 1, "SMTP 550")


# b90
def test_b90_whatsapp(conn: Connection, run: Any, meta: FakeMeta) -> None:
    set_up_whatsapp(conn)
    queue_message(conn, "Karim", None, "01712345678", "job", "x", "Update", "x" * 1500)
    process_once(run)
    r = row(conn, "whatsapp")
    assert (r["status"], r["provider_message_id"]) == ("sent", "wamid.TEST1")
    request = meta.requests[0]
    assert str(request.url) == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert request.headers["authorization"] == f"Bearer {WA_TOKEN}"
    body = json.loads(request.content)
    assert body["messaging_product"] == "whatsapp" and body["to"] == "8801712345678" and body["type"] == "template"
    assert body["template"]["name"] == "agency_update"
    assert body["template"]["language"] == {"code": "en_US"}
    param = body["template"]["components"][0]["parameters"][0]["text"]
    assert len(param) == 1000 and param.endswith("…")

    meta.status = 401
    queue_message(conn, "K", None, "+8801812345678", None, "y", "", "Hi")
    process_once(run)
    failed = conn.execute(text("SELECT * FROM notifications WHERE to_address = '+8801812345678'")).mappings().one()
    assert failed["status"] == "failed" and WA_TOKEN not in failed["last_error"]

    meta.status = 429
    queue_message(conn, "K", None, "01912345678", None, "z", "", "Hi")
    process_once(run)
    waiting = conn.execute(text("SELECT * FROM notifications WHERE to_address = '01912345678'")).mappings().one()
    assert (waiting["status"], waiting["tries"]) == ("queued", 1)

    queue_message(conn, "K", None, "12345", None, "bad", "", "Hi")
    process_once(run)
    bad = conn.execute(text("SELECT * FROM notifications WHERE to_address = '12345'")).mappings().one()
    assert (bad["status"], bad["last_error"]) == ("failed", "Invalid phone number")


# b91
def test_b91_each_message_sent_once(conn: Connection, run: Any, smtp: type[FakeSMTP]) -> None:
    # Claiming uses FOR UPDATE SKIP LOCKED and commits sending_since before sending; a row
    # claimed by another worker is skipped. The test transaction cannot run two workers in
    # parallel, so it checks that a claimed row is skipped and two rounds send once.
    set_up_email(conn)
    queue_message(conn, "A", "a@example.test", None, None, "x", "S", "B")
    queue_message(conn, "B", "b@example.test", None, None, "x", "S", "B")
    conn.execute(text("UPDATE notifications SET sending_since = now() WHERE to_address = 'b@example.test'"))
    process_once(run)
    process_once(run)
    assert [m["To"] for m in smtp.sent] == ["A <a@example.test>"]


# b92
def test_b92_stale_sending_goes_back(conn: Connection, run: Any, smtp: type[FakeSMTP]) -> None:
    set_up_email(conn)
    queue_message(conn, "A", "a@example.test", None, None, "x", "S", "B")
    conn.execute(text("UPDATE notifications SET sending_since = now() - interval '11 minutes'"))
    process_once(run)
    assert row(conn)["status"] == "sent"


# b93
def test_b93_list_masks_and_resend(client: TestClient, conn: Connection, act_as: Callable[..., Any], run: Any, smtp: type[FakeSMTP]) -> None:
    act_as("admin")
    queue_message(conn, "A", "a@example.test", None, "study", "email_code", "Your code", "Your code is 482913. Thanks")
    listed = client.get("/api/admin/notifications").json()["items"][0]
    assert "482913" not in listed["body"] and "••••••" in listed["body"]
    set_up_email(conn)
    smtp.error = smtplib.SMTPResponseException(550, b"no")
    process_once(run)
    failed = client.get("/api/admin/notifications?status=failed").json()["items"][0]
    assert client.post(f"/api/admin/notifications/{failed['id']}/resend").json()["status"] == "queued"
    smtp.error = None
    process_once(run)
    response = client.post(f"/api/admin/notifications/{failed['id']}/resend")
    assert response.status_code == 409
    assert audit_count(conn, "Message resent") == 1


# b94
def test_b94_test_buttons(api: FastAPI, client: TestClient, conn: Connection, act_as: Callable[..., Any], smtp: type[FakeSMTP], meta: FakeMeta) -> None:
    act_as("super_admin")
    not_set = client.post("/api/admin/settings/test-email", json={"to": "me@example.test"}).json()
    assert not_set == {"ok": False, "error": "Email is not set up"}
    set_up_email(conn)
    set_up_whatsapp(conn)
    assert client.post("/api/admin/settings/test-email", json={"to": "me@example.test"}).json() == {"ok": True}
    assert client.post("/api/admin/settings/test-whatsapp", json={"to": "01712345678"}).json() == {"ok": True}
    assert audit_count(conn, "Test email sent") == 2 and audit_count(conn, "Test WhatsApp sent") == 1
    assert conn.execute(text("SELECT count(*) FROM notifications")).scalar_one() == 0
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin")
    for path in ("/api/admin/settings/test-email", "/api/admin/settings/test-whatsapp"):
        assert staff.post(path, json={"to": "me@example.test"}).json()["code"] == "FORBIDDEN"


def test_settings_save_new_fields(client: TestClient, conn: Connection, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]) -> None:
    act_as("super_admin")
    body = settings_body()
    body["mail"].update(smtp_host="smtp.gmail.com", smtp_port=465, smtp_security="ssl", smtp_username="u", smtp_password=SMTP_PASSWORD)
    body["whatsapp"].update(phone_number_id="1234567890", template_name="agency_update", token=WA_TOKEN)
    saved = client.put("/api/settings", json=body)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["mail"]["smtp_host"] == "smtp.gmail.com" and view["mail"]["smtp_password"] == {"saved": True}
    assert view["whatsapp"]["token"] == {"saved": True}
    public = client.get("/api/settings/public").json()
    assert "smtp_host" not in public["mail"] and "phone_number_id" not in public["whatsapp"]
    for bad in ({"smtp_port": 0}, {"smtp_security": "tls"}, {"smtp_host": "bad host!"}):
        b = settings_body()
        b["mail"].update(bad)
        assert client.put("/api/settings", json=b).status_code == 422, bad
    b = settings_body()
    b["whatsapp"].update(api_version="21")
    assert client.put("/api/settings", json=b).status_code == 422


# b95
def test_b95_no_secrets_leak(client: TestClient, conn: Connection, act_as: Callable[..., Any], run: Any,
                             smtp: type[FakeSMTP], meta: FakeMeta, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    act_as("super_admin")
    set_up_email(conn)
    set_up_whatsapp(conn)
    smtp.error = smtplib.SMTPAuthenticationError(535, f"bad password {SMTP_PASSWORD}".encode())
    meta.status = 401
    queue_message(conn, "A", "a@example.test", "01712345678", None, "x", "S", "B")
    process_once(run)
    texts = [
        client.get("/api/admin/notifications").text,
        client.get("/api/settings").text,
        client.post("/api/admin/settings/test-email", json={"to": "me@example.test"}).text,
        client.post("/api/admin/settings/test-whatsapp", json={"to": "01712345678"}).text,
        json.dumps(conn.execute(text("SELECT last_error FROM notifications")).scalars().all()),
        json.dumps(conn.execute(text("SELECT detail FROM audit_log")).scalars().all()),
        caplog.text,
    ]
    for secret in (SMTP_PASSWORD, WA_TOKEN):
        assert all(secret not in t for t in texts), secret


# b96
def test_b96_outbox_only_through_queue_message() -> None:
    app_dir = BACKEND_DIR / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if re.search(r"INSERT\s+INTO\s+notifications", path.read_text(encoding="utf-8"), re.IGNORECASE)
    ]
    assert offenders == [str(Path("notify") / "outbox.py")]
