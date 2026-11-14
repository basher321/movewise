"""B07: payments, invoices, ledger, refunds and outstanding (b71-b85).

Gateway calls never reach the internet: app.payments.gateway.TRANSPORT is a fake transport
whose answers each test sets.
"""

import json
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.crypto import encrypt
from app.licence import today_dhaka
from app.payments import bkash, gateway
from auth_helpers import audit_count, license_modules, sign_in_admin_on, verified_applicant
from conftest import new_client
from test_catalog import university_body

SECRETS = {
    "sslcommerz.store_id": "STORE-ID-7731",
    "sslcommerz.store_password": "store-pass-9x8y",
    "bkash.app_key": "APP-KEY-5521",
    "bkash.app_secret": "APP-SECRET-0042",
    "bkash.username": "bk-user-31",
    "bkash.password": "bk-pass-77",
}
TOKEN = "ID-TOKEN-SECRET-123"
FEE = 100000
SITE = "http://localhost:3000"


class FakeGateway:
    """Answers SSLCommerz and bKash calls; tests change the answers."""

    def __init__(self) -> None:
        self.validation: dict[str, Any] = {}
        self.execute: Any = None  # dict, or an exception to raise
        self.status: dict[str, Any] = {}
        self.calls: list[str] = []
        self.next_bkash_id = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path.endswith("/gwprocess/v4/api.php"):
            form = parse_qs(request.content.decode())
            return httpx.Response(200, json={
                "status": "SUCCESS",
                "GatewayPageURL": "https://sandbox.sslcommerz.com/pay?t=" + form["tran_id"][0],
                "sessionkey": "SESSION-" + form["tran_id"][0],
            })
        if path.endswith("/validationserverAPI.php"):
            return httpx.Response(200, json=self.validation)
        if path.endswith("/token/grant"):
            return httpx.Response(200, json={"id_token": TOKEN, "expires_in": 3600, "statusCode": "0000"})
        if path.endswith("/checkout/create"):
            self.next_bkash_id += 1
            return httpx.Response(200, json={
                "paymentID": f"BKPAY{self.next_bkash_id}",
                "bkashURL": f"https://sandbox.bka.sh/pay/{self.next_bkash_id}",
                "statusCode": "0000",
            })
        if path.endswith("/checkout/execute"):
            if isinstance(self.execute, Exception):
                raise self.execute
            return httpx.Response(200, json=self.execute or {})
        if path.endswith("/payment/status"):
            return httpx.Response(200, json=self.status)
        return httpx.Response(404, json={})


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeGateway:
    fake_gateway = FakeGateway()
    monkeypatch.setattr(gateway, "TRANSPORT", httpx.MockTransport(fake_gateway.handle))
    bkash.clear_tokens()
    return fake_gateway


@pytest.fixture
def world(client: TestClient, conn: Connection, act_as: Callable[..., Any], fake: FakeGateway) -> dict[str, Any]:
    """Gateways on with saved secrets, a super admin, a university and a signed-in applicant."""
    license_modules(conn, "course", "study", "job")
    conn.execute(
        text("UPDATE settings SET sslcommerz_enabled = true, bkash_enabled = true, manual_enabled = true, "
             "invoice_prefix = 'INV' WHERE singleton = 'settings'")
    )
    for name, value in SECRETS.items():
        conn.execute(
            text("INSERT INTO settings_secrets (name, ciphertext) VALUES (:n, :c)"), {"n": name, "c": encrypt(name, value)}
        )
    act_as("super_admin")
    uni = client.post("/api/admin/universities", json=university_body()).json()
    verified_applicant(client, conn, "study", "payer@example.test")
    return {"uni": uni}


def new_app(client: TestClient, world: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    slug = world["uni"]["slug"]
    if name:
        slug = client.post("/api/admin/universities", json=university_body(name=name)).json()["slug"]
    return dict(client.post("/api/me/study/applications", json={"item_slug": slug, "answers": {}}).json())


def pay(client: TestClient, app_id: str, method: str = "sslcommerz", **extra: Any) -> Any:
    body = {"method": method, "phone": "01712345678", **extra}
    return client.post(f"/api/me/study/applications/{app_id}/pay", json=body)


def payment_row(conn: Connection, payment_id: str) -> Any:
    return conn.execute(text("SELECT * FROM payments WHERE id = :id"), {"id": payment_id}).mappings().one()


def valid(payment: Any, **changes: Any) -> dict[str, Any]:
    amount = f"{payment['amount_poisha'] // 100}.{payment['amount_poisha'] % 100:02d}"
    return {"status": "VALID", "tran_id": payment["tran_id"], "amount": amount, "currency": "BDT",
            "currency_type": "BDT", "currency_amount": amount, "risk_level": "0", "bank_tran_id": "BANK-1",
            "store_id": SECRETS["sslcommerz.store_id"], "card_no": "4111XXXXXXXX1111", **changes}


def ssl_callback(client: TestClient, kind: str, payment: Any, val_id: str = "VAL-1") -> Any:
    return client.post(
        f"/api/pay/sslcommerz/{kind}",
        data={"tran_id": payment["tran_id"], "val_id": val_id, "status": "VALID"},
        headers={"Origin": "https://sandbox.sslcommerz.com"},
        follow_redirects=False,
    )


def counts(conn: Connection) -> tuple[int, int, int]:
    return (
        conn.execute(text("SELECT count(*) FROM invoices")).scalar_one(),
        conn.execute(text("SELECT count(*) FROM ledger_entries")).scalar_one(),
        conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'payment_received'")).scalar_one(),
    )


def paid_by_ssl(client: TestClient, conn: Connection, fake: FakeGateway, app: dict[str, Any]) -> Any:
    started = pay(client, app["id"]).json()
    payment = payment_row(conn, started["payment_id"])
    fake.validation = valid(payment)
    assert ssl_callback(client, "success", payment).status_code == 303
    return payment_row(conn, started["payment_id"])


# b71
@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM payments WHERE true",
        "DELETE FROM invoices WHERE true",
        "DELETE FROM ledger_entries WHERE true",
        "DELETE FROM refunds WHERE true",
        "UPDATE ledger_entries SET party = 'x' WHERE true",
        "UPDATE payment_events SET kind = 'x' WHERE true",
        "UPDATE invoices SET amount_poisha = 1 WHERE true",
    ],
)
def test_b71_money_records_are_append_only(
    client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway, sql: str
) -> None:
    payment = paid_by_ssl(client, conn, fake, new_app(client, world))
    client.post(f"/api/me/study/refunds", json={"invoice_no": f"INV-{today_dhaka().year}-0001", "reason": "x"})
    assert payment["status"] == "paid"
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text(sql))


# b72
def test_b72_only_one_live_payment(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    # Starts lock the application row, so two at once run one after the other. The test
    # transaction cannot run two requests in parallel; it checks the outcome of back-to-back starts.
    app = new_app(client, world)
    first = pay(client, app["id"]).json()
    second = pay(client, app["id"]).json()
    live = conn.execute(
        text("SELECT id::text FROM payments WHERE ref_id = :r AND status IN ('initiated', 'pending_verify', 'paid')"),
        {"r": app["id"]},
    ).scalars().all()
    assert live == [second["payment_id"]]
    assert payment_row(conn, first["payment_id"])["status"] == "abandoned"


# b73
def test_b73_sslcommerz_success_once(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    app = new_app(client, world)
    started = pay(client, app["id"]).json()
    assert started["redirect_url"].startswith("https://sandbox.sslcommerz.com/")
    payment = payment_row(conn, started["payment_id"])
    assert payment["amount_poisha"] == FEE
    fake.validation = valid(payment)
    response = ssl_callback(client, "success", payment)
    assert response.headers["location"] == f"{SITE}/payment/result?id={payment['id']}"
    paid = payment_row(conn, payment["id"])
    assert paid["status"] == "paid" and paid["gateway_ref"] == "BANK-1"
    no = conn.execute(text("SELECT no FROM invoices WHERE payment_id = :p"), {"p": payment["id"]}).scalar_one()
    assert no == f"INV-{today_dhaka().year}-0001"
    assert counts(conn) == (1, 1, 1)
    detail = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert detail["fee_paid"] is True and detail["history"][0]["text"] == "Application fee paid (৳1,000)"
    assert client.get(f"/api/me/payments/{payment['id']}").json()["invoice_no"] == no

    ssl_callback(client, "success", payment)
    client.post("/api/pay/sslcommerz/ipn", data={"tran_id": payment["tran_id"], "val_id": "VAL-1"})
    assert counts(conn) == (1, 1, 1)


# b74
def test_b74_mismatch_and_invalid(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    started = pay(client, new_app(client, world)["id"]).json()
    payment = payment_row(conn, started["payment_id"])
    fake.validation = valid(payment, amount="10.00", currency_amount="10.00")
    ssl_callback(client, "success", payment)
    assert payment_row(conn, payment["id"])["status"] == "failed"
    assert conn.execute(text("SELECT kind FROM payment_events WHERE payment_id = :p AND kind = 'mismatch'"), {"p": payment["id"]}).first()

    other = payment_row(conn, pay(client, new_app(client, world, "Second Uni")["id"]).json()["payment_id"])
    fake.validation = {"status": "INVALID_TRANSACTION"}
    ssl_callback(client, "success", other)
    assert payment_row(conn, other["id"])["status"] != "paid"
    assert counts(conn)[0] == 0


def test_validation_unreachable_keeps_initiated(
    client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    payment = payment_row(conn, pay(client, new_app(client, world)["id"]).json()["payment_id"])

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("down")

    monkeypatch.setattr(gateway, "TRANSPORT", httpx.MockTransport(down))
    assert ssl_callback(client, "success", payment).status_code == 303
    assert payment_row(conn, payment["id"])["status"] == "initiated"


def test_unknown_callback_and_fail_cancel(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    unknown = client.post("/api/pay/sslcommerz/success", data={"tran_id": "NOPE1234"}, follow_redirects=False)
    assert unknown.status_code == 404
    assert client.get("/api/pay/bkash/callback?paymentID=NOPE&status=success", follow_redirects=False).status_code == 404
    payment = payment_row(conn, pay(client, new_app(client, world)["id"]).json()["payment_id"])
    ssl_callback(client, "cancel", payment)
    assert payment_row(conn, payment["id"])["status"] == "cancelled"
    ssl_callback(client, "fail", payment)
    assert payment_row(conn, payment["id"])["status"] == "cancelled"


# b75
def test_b75_high_risk(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    payment = payment_row(conn, pay(client, new_app(client, world)["id"]).json()["payment_id"])
    fake.validation = valid(payment, risk_level="1")
    ssl_callback(client, "success", payment)
    row = payment_row(conn, payment["id"])
    assert row["status"] == "pending_verify" and row["decision_note"].startswith("High-risk")
    finance = new_client(api)
    sign_in_admin_on(finance, conn, "finance")
    assert [p["id"] for p in finance.get("/api/admin/payments/pending").json()] == [str(payment["id"])]
    assert finance.post(f"/api/admin/payments/{payment['id']}/verify").json()["status"] == "paid"
    assert finance.post(f"/api/admin/payments/{payment['id']}/verify").status_code == 409


# b76
def test_b76_bkash(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    def start(name: str) -> Any:
        started = pay(client, new_app(client, world, name)["id"], method="bkash").json()
        assert started["redirect_url"].startswith("https://sandbox.bka.sh/")
        return payment_row(conn, started["payment_id"])

    def callback(payment: Any, status: str) -> None:
        response = client.get(
            f"/api/pay/bkash/callback?paymentID={payment['gateway_session']}&status={status}", follow_redirects=False
        )
        assert response.status_code == 303

    def completed(payment: Any, trx: str) -> dict[str, Any]:
        return {"transactionStatus": "Completed", "amount": "1000.00", "merchantInvoiceNumber": payment["tran_id"],
                "trxID": trx, "statusCode": "0000"}

    first = start("Uni One")
    fake.execute = completed(first, "TRX-1")
    callback(first, "success")
    assert (payment_row(conn, first["id"])["status"], payment_row(conn, first["id"])["gateway_ref"]) == ("paid", "TRX-1")

    second = start("Uni Two")
    fake.execute = httpx.ReadTimeout("slow")
    fake.status = completed(second, "TRX-2")
    callback(second, "success")
    assert payment_row(conn, second["id"])["status"] == "paid"
    assert any(p.endswith("/payment/status") for p in fake.calls)

    third = start("Uni Three")
    callback(third, "failure")
    assert payment_row(conn, third["id"])["status"] == "failed"


# b77
def test_b77_late_success_is_duplicate(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    app = new_app(client, world)
    first = payment_row(conn, pay(client, app["id"]).json()["payment_id"])
    second = paid_by_ssl(client, conn, fake, app)
    assert payment_row(conn, first["id"])["status"] == "abandoned"
    fake.validation = valid(first)
    ssl_callback(client, "success", first)
    assert payment_row(conn, first["id"])["status"] == "duplicate"
    assert counts(conn)[0] == 1
    refund = conn.execute(text("SELECT * FROM refunds WHERE payment_id = :p"), {"p": first["id"]}).mappings().one()
    assert refund["reason"] == "Duplicate payment - refund required" and refund["invoice_no"] is None
    assert second["status"] == "paid"


# b78
def test_b78_invoice_numbers_gap_free(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    # The counter row is locked per transaction (INSERT .. ON CONFLICT DO UPDATE), so parallel
    # payments wait for each other. The test transaction runs them one after the other.
    for i in range(20):
        paid_by_ssl(client, conn, fake, new_app(client, world, f"Uni {i}"))
    numbers = conn.execute(text("SELECT no FROM invoices ORDER BY no")).scalars().all()
    year = today_dhaka().year
    assert numbers == [f"INV-{year}-{n:04d}" for n in range(1, 21)]


# b79
def test_b79_manual(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    assert pay(client, app["id"], method="manual").status_code == 422
    assert pay(client, app["id"], method="manual", manual_ref="BANK-REF-1", phone="12345").status_code == 422
    started = pay(client, app["id"], method="manual", manual_ref="BANK-REF-1").json()
    assert started["status"] == "pending_verify"
    assert pay(client, app["id"], method="manual", manual_ref="AGAIN").status_code == 409
    assert client.post(f"/api/admin/payments/{started['payment_id']}/reject", json={"reason": " "}).status_code == 422
    assert client.post(f"/api/admin/payments/{started['payment_id']}/verify").json()["status"] == "paid"

    other = new_app(client, world, "Other Uni")
    second = pay(client, other["id"], method="manual", manual_ref="BANK-REF-2").json()
    rejected = client.post(f"/api/admin/payments/{second['payment_id']}/reject", json={"reason": "Not in our bank"})
    assert rejected.json()["status"] == "rejected"
    assert pay(client, other["id"], method="manual", manual_ref="BANK-REF-3").status_code == 200


def test_method_must_be_on_and_set_up(client: TestClient, conn: Connection, world: dict[str, Any]) -> None:
    app = new_app(client, world)
    conn.execute(text("UPDATE settings SET bkash_enabled = false WHERE singleton = 'settings'"))
    assert pay(client, app["id"], method="bkash").status_code == 422
    conn.execute(text("UPDATE settings SET bkash_enabled = true WHERE singleton = 'settings'"))
    conn.execute(text("UPDATE settings_secrets SET ciphertext = 'broken' WHERE name = 'bkash.app_key'"))
    assert "not set up" in pay(client, app["id"], method="bkash").json()["message"]


# b80
def test_b80_refund(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    paid_by_ssl(client, conn, fake, new_app(client, world))
    no = f"INV-{today_dhaka().year}-0001"
    first = client.post("/api/me/study/refunds", json={"invoice_no": no, "reason": "Changed my plan"})
    assert first.status_code == 200
    assert client.post("/api/me/study/refunds", json={"invoice_no": no, "reason": "Again"}).status_code == 409
    url = f"/api/admin/refunds/{first.json()['id']}/approve"
    assert client.post(url, json={"refund_method": "bKash", "refund_ref": " "}).status_code == 422
    assert client.post(url, json={"refund_method": "bKash", "refund_ref": "RF-1"}).json()["status"] == "approved"
    assert client.post(url, json={"refund_method": "bKash", "refund_ref": "RF-1"}).status_code == 409
    out = conn.execute(text("SELECT * FROM ledger_entries WHERE direction = 'out'")).mappings().one()
    assert out["category"] == "refund" and out["amount_poisha"] == FEE
    assert client.get(f"/api/me/study/invoices/{no}").json()["status"] == "refunded"
    assert client.get("/api/admin/ledger/summary").json()["balance_all_time_poisha"] == 0


# b81
def test_b81_ledger(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    paid_by_ssl(client, conn, fake, new_app(client, world))
    today = today_dhaka()
    entry = {"direction": "out", "category": "rent", "date": today.isoformat(), "amount_poisha": 500000,
             "party": "Landlord", "method": "Cash", "note": "October"}
    for bad in ({"amount_poisha": 0}, {"amount_poisha": 1250}, {"amount_poisha": 12.5},
                {"date": (today + timedelta(days=1)).isoformat()}, {"party": " "}, {"category": "course"}):
        assert client.post("/api/admin/ledger", json={**entry, **bad}).status_code == 422, bad
    added = client.post("/api/admin/ledger", json=entry).json()
    summary = client.get("/api/admin/ledger/summary").json()
    assert summary["balance_all_time_poisha"] == FEE - 500000
    assert summary["by_expense"] == {"rent": 500000}

    assert client.post(f"/api/admin/ledger/{added['id']}/reverse", json={"reason": " "}).status_code == 422
    assert client.post(f"/api/admin/ledger/{added['id']}/reverse", json={"reason": "Wrong month"}).status_code == 200
    assert client.post(f"/api/admin/ledger/{added['id']}/reverse", json={"reason": "Again"}).status_code == 409
    assert client.get("/api/admin/ledger/summary").json()["balance_all_time_poisha"] == FEE
    auto = conn.execute(text("SELECT id FROM ledger_entries WHERE auto")).scalar_one()
    assert client.post(f"/api/admin/ledger/{auto}/reverse", json={"reason": "x"}).status_code == 409
    listed = client.get("/api/admin/ledger").json()["items"]
    assert listed[0]["balance_poisha"] == FEE and any(e["reversed"] for e in listed)

    csv = client.get("/api/admin/ledger.csv")
    assert csv.content.startswith(b"\xef\xbb\xbf")
    lines = csv.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Date,Type,Category,Party,Email,Description,Method,Reference,Amount"
    assert any(line.endswith(",-5000.00") for line in lines)
    assert any(line.endswith(",1000.00") for line in lines)


# b82
def test_b82_fee_change_after_start(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    app = new_app(client, world)
    started = pay(client, app["id"]).json()
    client.put("/api/admin/fees", json={"study": {world["uni"]["id"]: 300000}})
    payment = payment_row(conn, started["payment_id"])
    assert payment["amount_poisha"] == FEE
    fake.validation = valid(payment)
    ssl_callback(client, "success", payment)
    assert conn.execute(text("SELECT amount_poisha FROM invoices")).scalar_one() == FEE


# b83
def test_b83_section_admin(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    payment = paid_by_ssl(client, conn, fake, new_app(client, world))
    no = f"INV-{today_dhaka().year}-0001"
    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    assert staff.get("/api/admin/invoices?module=study").json()["total"] == 1
    assert staff.get(f"/api/admin/invoices/{no}").status_code == 200
    assert staff.get("/api/admin/invoices?module=job").status_code == 403
    for method, path in (
        ("post", f"/api/admin/payments/{payment['id']}/verify"),
        ("get", "/api/admin/payments/pending"),
        ("get", "/api/admin/refunds"),
        ("get", "/api/admin/ledger"),
        ("get", "/api/admin/ledger/summary"),
        ("get", "/api/admin/ledger.csv"),
        ("get", "/api/admin/outstanding"),
    ):
        response = staff.request(method, path)
        assert response.status_code == 403, path
        assert response.json()["code"] == "FORBIDDEN"
    job_staff = new_client(api)
    sign_in_admin_on(job_staff, conn, "admin", ["job"])
    assert job_staff.get(f"/api/admin/invoices/{no}").status_code == 403


# b84
def test_b84_no_secrets_anywhere(
    client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bodies: list[str] = []
    app = new_app(client, world)
    started = pay(client, app["id"])
    bodies.append(started.text)
    payment = payment_row(conn, started.json()["payment_id"])
    fake.validation = valid(payment)
    bodies.append(ssl_callback(client, "success", payment).text)
    bk = pay(client, new_app(client, world, "Bk Uni")["id"], method="bkash")
    bodies.append(bk.text)
    bk_row = payment_row(conn, bk.json()["payment_id"])
    fake.execute = {"transactionStatus": "Completed", "amount": "1000.00", "merchantInvoiceNumber": bk_row["tran_id"],
                    "trxID": "TRX-9", "id_token": TOKEN, "app_key": SECRETS["bkash.app_key"]}
    client.get(f"/api/pay/bkash/callback?paymentID={bk_row['gateway_session']}&status=success", follow_redirects=False)
    for path in ("/api/admin/payments/pending", "/api/admin/ledger", "/api/admin/invoices", "/api/settings",
                 f"/api/me/payments/{payment['id']}"):
        bodies.append(client.get(path).text)
    events = json.dumps(conn.execute(text("SELECT detail FROM payment_events")).scalars().all())
    assert "4111" not in events
    haystack = "\n".join(bodies) + events + caplog.text
    for secret in (*SECRETS.values(), TOKEN):
        assert secret not in haystack, secret


# b85
def test_b85_one_audit_row_per_change(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    app = new_app(client, world)

    def changes(call: Callable[[], Any], expected: int = 1) -> Any:
        before = audit_count(conn)
        result = call()
        assert audit_count(conn) == before + expected
        return result

    started = changes(lambda: pay(client, app["id"]).json())
    payment = payment_row(conn, started["payment_id"])
    fake.validation = valid(payment)
    changes(lambda: ssl_callback(client, "success", payment))
    no = f"INV-{today_dhaka().year}-0001"
    refund = changes(lambda: client.post("/api/me/study/refunds", json={"invoice_no": no, "reason": "x"}).json())
    changes(lambda: client.post(f"/api/admin/refunds/{refund['id']}/decline", json={"reason": "Service used"}))
    entry = {"direction": "in", "category": "otherin", "date": today_dhaka().isoformat(), "amount_poisha": 1000,
             "party": "Walk-in", "method": "Cash"}
    added = changes(lambda: client.post("/api/admin/ledger", json=entry).json())
    changes(lambda: client.post(f"/api/admin/ledger/{added['id']}/reverse", json={"reason": "typo"}))
    other = new_app(client, world, "Remind Uni")
    changes(lambda: client.post("/api/admin/outstanding/not-a-uuid/remind"), 0)
    applicant = conn.execute(text("SELECT applicant_id FROM applications WHERE id = :id"), {"id": other["id"]}).scalar_one()
    outstanding = client.get("/api/admin/outstanding").json()
    assert outstanding["total_poisha"] == FEE
    changes(lambda: client.post(f"/api/admin/outstanding/{applicant}/remind"))


def test_application_detail_shows_payment_and_invoice(client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    app = new_app(client, world)
    before = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert before["payment"] is None and before["invoice"] is None and before["answers"] == {}
    paid_by_ssl(client, conn, fake, app)
    after = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert after["payment"]["status"] == "paid" and after["payment"]["method"] == "sslcommerz"
    assert after["invoice"]["no"] == f"INV-{today_dhaka().year}-0001"
    assert after["invoice"]["email_status"] == "queued"


def test_applicant_without_email_can_pay(api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway) -> None:
    payer = new_client(api)
    signup = payer.post("/api/auth/applicant/study/signup", json={"name": "No Mail", "username": "no.mail", "password": "secret12"})
    assert signup.status_code == 200 and signup.json()["email"] is None
    app = payer.post("/api/me/study/applications", json={"item_slug": world["uni"]["slug"], "answers": {}}).json()
    url = f"/api/me/study/applications/{app['id']}/pay"
    no_company_email = payer.post(url, json={"method": "sslcommerz", "phone": "01712345678"})
    assert no_company_email.status_code == 422 and "add your email" in no_company_email.json()["message"]
    conn.execute(text("UPDATE settings SET email = 'office@agency.test' WHERE singleton = 'settings'"))
    started = payer.post(url, json={"method": "sslcommerz", "phone": "01712345678"})
    assert started.status_code == 200
    payment = payment_row(conn, started.json()["payment_id"])
    fake.validation = valid(payment)
    ssl_callback(client, "success", payment)
    assert conn.execute(text("SELECT email FROM invoices")).scalar_one() == ""
    # The receipt goes by WhatsApp only when there is a phone; no email row without an email.
    assert conn.execute(text("SELECT count(*) FROM notifications WHERE event = 'payment_received' AND channel = 'email'")).scalar_one() == 0


# Self Apply: a separate self-apply fee, then the official link; no documents.
def test_self_apply_pays_its_own_fee_then_gets_link(
    client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway
) -> None:
    slug = world["uni"]["slug"]
    refused = client.post("/api/me/study/applications", json={"item_slug": slug, "answers": {}, "self_apply": True})
    assert refused.status_code == 409 and refused.json()["code"] == "CONFLICT"

    uni = client.put(
        f"/api/admin/universities/{world['uni']['id']}", json=university_body(self_apply_fee_poisha=50000)
    ).json()
    assert uni["self_apply_fee_poisha"] == 50000
    assert client.get(f"/api/universities/{slug}").json()["self_apply_fee_poisha"] == 50000

    app = client.post("/api/me/study/applications", json={"item_slug": slug, "answers": {}, "self_apply": True}).json()
    assert app["self_apply"] is True and app["fee_poisha"] == 50000
    assert "apply_link" not in app
    doc = client.post(
        f"/api/me/study/applications/{app['id']}/documents",
        data={"type": "Valid passport"},
        files={"file": ("p.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
    )
    assert doc.status_code == 409

    payment = paid_by_ssl(client, conn, fake, app)
    assert payment["amount_poisha"] == 50000 and payment["status"] == "paid"
    assert payment["purpose"].startswith("Self-apply fee - ")
    after = client.get(f"/api/me/study/applications/{app['id']}").json()
    assert after["fee_paid"] is True and after["apply_link"] == "https://apply.example.test"


# Case fee: the super admin sets a fee for one case before any payment starts.
def test_case_fee_set_before_payment_only(
    api: FastAPI, client: TestClient, conn: Connection, world: dict[str, Any], fake: FakeGateway
) -> None:
    app = new_app(client, world)
    url = f"/api/admin/applications/{app['id']}/fee"
    case = client.get(f"/api/admin/applications/{app['id']}").json()
    assert (case["item_fee_poisha"], case["fee_override_poisha"], case["case_fee_poisha"], case["fee_locked"]) == (
        FEE, None, FEE, False
    )
    for bad in (0, -100, 150050):
        response = client.put(url, json={"fee_poisha": bad})
        assert response.status_code == 422 and response.json()["code"] == "VALIDATION", bad

    before = audit_count(conn)
    case = client.put(url, json={"fee_poisha": 250000}).json()
    assert (case["fee_override_poisha"], case["case_fee_poisha"]) == (250000, 250000)
    assert audit_count(conn) == before + 1
    assert client.get(f"/api/me/study/applications/{app['id']}").json()["fee_poisha"] == 250000
    # The item fee changing later does not change this case.
    client.put("/api/admin/fees", json={"study": {world["uni"]["id"]: 300000}})
    assert client.get(f"/api/admin/applications/{app['id']}").json()["case_fee_poisha"] == 250000

    staff = new_client(api)
    sign_in_admin_on(staff, conn, "admin", ["study"])
    assert staff.put(url, json={"fee_poisha": 1000}).json()["code"] == "FORBIDDEN"

    started = pay(client, app["id"]).json()
    assert payment_row(conn, started["payment_id"])["amount_poisha"] == 250000
    response = client.put(url, json={"fee_poisha": 100})
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT"
    assert client.get(f"/api/admin/applications/{app['id']}").json()["fee_locked"] is True

    # Back to the item fee (null): the second university has the default fee.
    other = new_app(client, world, name="Second University")
    other_url = f"/api/admin/applications/{other['id']}/fee"
    client.put(other_url, json={"fee_poisha": 50000})
    case = client.put(other_url, json={"fee_poisha": None}).json()
    assert (case["fee_override_poisha"], case["case_fee_poisha"]) == (None, FEE)
