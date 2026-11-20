"""B26: the EPS payment gateway (b261-b272).

EPS calls never reach the internet: app.payments.gateway.TRANSPORT is a fake EPS whose answers
each test sets. Test values only; the real EPS keys are typed into Settings by the owner.
"""

import base64
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.crypto import encrypt
from app.payments import eps, gateway
from auth_helpers import audit_count
from test_payments import FakeGateway, counts, fake, new_app, payment_row, world  # noqa: F401

EPS_SECRETS = {
    "eps.store_id": "EPS-STORE-4410",
    "eps.username": "eps-user@example.test",
    "eps.password": "eps-pass-2231",
    "eps.hash_key": "EPS-HASH-KEY-77aa=",
}
EPS_TOKEN = "EPS-TOKEN-SECRET-555"


class FakeEps:
    """Answers the three EPS calls; tests change the answers."""

    def __init__(self) -> None:
        self.status: dict[str, Any] = {}
        self.start_errors: list[dict[str, Any]] = []  # answers given before a good start
        self.status_codes: list[int] = []  # HTTP codes given before a good status answer
        self.token_calls = 0
        self.requests: list[httpx.Request] = []
        self.next_id = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/Auth/GetToken":
            self.token_calls += 1
            return httpx.Response(200, json={"token": EPS_TOKEN, "expireDate": "2099-01-01T00:00:00.0",
                                             "errorMessage": None, "errorCode": None})
        if path == "/v1/EPSEngine/InitializeEPS":
            if self.start_errors:
                return httpx.Response(200, json=self.start_errors.pop(0))
            self.next_id += 1
            return httpx.Response(200, json={
                "TransactionId": f"eps-session-{self.next_id}",
                "RedirectURL": f"https://sandboxpg.eps.com.bd/PG?data=eps-session-{self.next_id}",
                "ErrorMessage": "", "ErrorCode": None, "FinancialEntityList": None,
            })
        if path == "/v1/EPSEngine/CheckMerchantTransactionStatus":
            if self.status_codes:
                return httpx.Response(self.status_codes.pop(0))
            return httpx.Response(200, json=self.status)
        return httpx.Response(404, json={})


@pytest.fixture
def fake_eps(monkeypatch: pytest.MonkeyPatch, fake: FakeGateway) -> FakeEps:  # noqa: F811
    fake_gateway = FakeEps()
    monkeypatch.setattr(gateway, "TRANSPORT", httpx.MockTransport(fake_gateway.handle))
    monkeypatch.setattr(eps, "RETRY_PAUSE", 0)
    eps.clear_tokens()
    return fake_gateway


@pytest.fixture
def eps_world(conn: Connection, world: dict[str, Any], fake_eps: FakeEps) -> dict[str, Any]:  # noqa: F811
    conn.execute(text("UPDATE settings SET eps_enabled = true, eps_sandbox = true WHERE singleton = 'settings'"))
    for name, value in EPS_SECRETS.items():
        conn.execute(
            text("INSERT INTO app_secrets (name, ciphertext) VALUES (:n, :c)"), {"n": name, "c": encrypt(name, value)}
        )
    return world


def pay_eps(client: TestClient, world: dict[str, Any], name: str | None = None) -> Any:
    app = new_app(client, world, name)
    return client.post(f"/api/me/study/applications/{app['id']}/pay", json={"method": "eps", "phone": "01712345678"})


def success(payment: Any, **changes: Any) -> dict[str, Any]:
    amount = f"{payment['amount_poisha'] // 100}.{payment['amount_poisha'] % 100:02d}"
    return {"MerchantTransactionId": payment["tran_id"], "EPSTransactionId": "EPS-TRX-1", "Status": "Success",
            "TotalAmount": amount, "FinancialEntity": "bKash", "ErrorCode": None, "ErrorMessage": None, **changes}


def back(client: TestClient, payment: Any, outcome: str, query: str = "") -> Any:
    return client.get(f"/api/pay/eps/return/{payment['tran_id']}/{outcome}{query}", follow_redirects=False)


def expected_hash(key: str, value: str) -> str:
    return base64.b64encode(hmac.new(key.encode(), value.encode(), hashlib.sha512).digest()).decode()


# b261
def test_b261_migration(client: TestClient, conn: Connection, eps_world: dict[str, Any]) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    assert payment["method"] == "eps"
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("UPDATE payments SET method = 'paypal' WHERE id = :id"), {"id": payment["id"]})
    # EPS alone counts as a payment method that is on.
    conn.execute(text(
        "UPDATE settings SET sslcommerz_enabled = false, bkash_enabled = false, nagad_enabled = false, "
        "manual_enabled = false WHERE singleton = 'settings'"
    ))
    with pytest.raises(DBAPIError):
        with conn.begin_nested():
            conn.execute(text("UPDATE settings SET eps_enabled = false WHERE singleton = 'settings'"))


# b262
def test_b262_x_hash() -> None:
    assert eps.x_hash("key-1", "1234567890123456") == expected_hash("key-1", "1234567890123456")
    assert eps.x_hash("key-1", "a") != eps.x_hash("key-2", "a")


# b263
def test_b263_start(client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps) -> None:
    first = pay_eps(client, eps_world)
    assert first.status_code == 200, first.text
    pay_eps(client, eps_world, "Second Uni")
    assert fake_eps.token_calls == 1
    payment = payment_row(conn, first.json()["payment_id"])
    assert payment["method"] == "eps" and payment["status"] == "initiated"
    assert payment["tran_id"].isdigit() and len(payment["tran_id"]) == 16
    assert first.json()["redirect_url"] == "https://sandboxpg.eps.com.bd/PG?data=eps-session-1"
    assert payment["gateway_session"] == "eps-session-1"
    token_call, start_call = fake_eps.requests[0], fake_eps.requests[1]
    assert token_call.url.host == "sandboxpgapi.eps.com.bd"
    assert token_call.headers["x-hash"] == expected_hash(EPS_SECRETS["eps.hash_key"], EPS_SECRETS["eps.username"])
    assert start_call.headers["x-hash"] == expected_hash(EPS_SECRETS["eps.hash_key"], payment["tran_id"])
    assert start_call.headers["authorization"] == f"Bearer {EPS_TOKEN}"
    body = json.loads(start_call.content)
    assert "merchantId" not in body
    assert body["merchantTransactionId"] == body["CustomerOrderId"] == payment["tran_id"]
    assert body["totalAmount"] == f"{payment['amount_poisha'] // 100}.{payment['amount_poisha'] % 100:02d}"
    assert body["transactionTypeId"] == 1 and body["storeId"] == EPS_SECRETS["eps.store_id"]
    assert body["successUrl"].endswith(f"/api/pay/eps/return/{payment['tran_id']}/success")
    assert body["failUrl"].endswith("/fail") and body["cancelUrl"].endswith("/cancel")


def test_start_retries_twice_with_a_new_tran_id(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps
) -> None:
    refused = {"TransactionId": None, "RedirectURL": None, "ErrorCode": 500,
               "ErrorMessage": "An error occured while initalizing the transaction."}
    fake_eps.start_errors = [dict(refused), dict(refused)]
    started = pay_eps(client, eps_world)
    assert started.status_code == 200
    starts = [r for r in fake_eps.requests if r.url.path.endswith("InitializeEPS")]
    ids = [json.loads(r.content)["merchantTransactionId"] for r in starts]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert payment_row(conn, started.json()["payment_id"])["tran_id"] == ids[2]
    fake_eps.start_errors = [dict(refused), dict(refused), dict(refused)]
    assert pay_eps(client, eps_world, "Third Uni").status_code == 500


# b264
def test_b264_success_once(client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps) -> None:
    started = pay_eps(client, eps_world).json()
    payment = payment_row(conn, started["payment_id"])
    before = counts(conn)
    fake_eps.status = success(payment)
    response = back(client, payment, "success", "?status=Success&EPSTransactionId=EPS-TRX-1")
    assert response.status_code == 303 and response.headers["location"].endswith(f"/payment/result?id={payment['id']}")
    paid = payment_row(conn, payment["id"])
    assert paid["status"] == "paid" and paid["gateway_ref"] == "EPS-TRX-1"
    after = counts(conn)
    assert after == (before[0] + 1, before[1] + 1, after[2]) and after[2] > before[2]
    assert back(client, payment, "success").status_code == 303
    assert counts(conn) == after
    invoice = conn.execute(text("SELECT method FROM invoices WHERE payment_id = :p"), {"p": payment["id"]}).scalar_one()
    assert invoice == "EPS"


def test_a_success_address_alone_never_pays(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps
) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    fake_eps.status = success(payment, Status="Cancel")  # what EPS says for a started, unpaid payment
    back(client, payment, "success", "?status=Success")
    assert payment_row(conn, payment["id"])["status"] == "initiated"
    assert client.get(f"/api/me/payments/{payment['id']}").json()["status"] == "initiated"


# b265
def test_b265_mismatch(client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    before = counts(conn)
    fake_eps.status = success(payment, TotalAmount="1.00")
    back(client, payment, "success")
    assert payment_row(conn, payment["id"])["status"] == "failed"
    assert counts(conn)[:2] == before[:2]
    kinds = conn.execute(text("SELECT kind FROM payment_events WHERE payment_id = :p"), {"p": payment["id"]}).scalars().all()
    assert "mismatch" in kinds


# b266
def test_b266_fail_cancel_and_unclear(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps
) -> None:
    fake_eps.status = {"ErrorCode": 400, "ErrorMessage": "Transaction Not Found."}
    one = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    back(client, one, "fail")
    assert payment_row(conn, one["id"])["status"] == "failed"
    two = payment_row(conn, pay_eps(client, eps_world, "Two Uni").json()["payment_id"])
    back(client, two, "cancel")
    assert payment_row(conn, two["id"])["status"] == "cancelled"
    three = payment_row(conn, pay_eps(client, eps_world, "Three Uni").json()["payment_id"])
    back(client, three, "success")
    assert payment_row(conn, three["id"])["status"] == "initiated"


def test_old_unpaid_payment_ends_on_status_check(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps
) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    fake_eps.status = success(payment, Status="Cancel")
    conn.execute(text("UPDATE payments SET created_at = now() - interval '31 minutes' WHERE id = :id"), {"id": payment["id"]})
    assert client.get(f"/api/me/payments/{payment['id']}").json()["status"] == "cancelled"


def test_late_success_after_cancel_is_still_recorded(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps
) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    fake_eps.status = success(payment, Status="Cancel")
    back(client, payment, "cancel")
    assert payment_row(conn, payment["id"])["status"] == "cancelled"
    fake_eps.status = success(payment)
    back(client, payment, "success")
    assert payment_row(conn, payment["id"])["status"] == "paid"


# b267
def test_b267_unknown_return(client: TestClient, conn: Connection, eps_world: dict[str, Any]) -> None:
    before = conn.execute(text("SELECT count(*) FROM payment_events")).scalar_one()
    assert client.get("/api/pay/eps/return/9999999999999999/success", follow_redirects=False).status_code == 404
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    assert back(client, payment, "maybe").status_code == 404
    after = conn.execute(text("SELECT count(*) FROM payment_events")).scalar_one()
    assert after == before + 1  # only the "started" event of the new payment


# b268
@pytest.mark.parametrize("code", [302, 401])
def test_b268_token_renewed_once(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps, code: int
) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    fake_eps.status = success(payment)
    fake_eps.status_codes = [code]
    back(client, payment, "success")
    assert fake_eps.token_calls == 2
    assert payment_row(conn, payment["id"])["status"] == "paid"


# b269
def test_b269_settings(
    client: TestClient, conn: Connection, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]
) -> None:
    act_as("super_admin")
    body = settings_body()
    body["gateways"]["eps"] = {"enabled": True, "sandbox": True, "store_id": " S-1 ", "username": "u"}
    response = client.put("/api/settings", json=body)
    assert response.status_code == 422 and "password, hash key" in response.json()["message"]
    body["gateways"]["eps"].update(password="p", hash_key="h")
    saved = client.put("/api/settings", json=body)
    assert saved.status_code == 200, saved.text
    eps_view = saved.json()["gateways"]["eps"]
    assert eps_view["enabled"] is True and eps_view["store_id"] == {"saved": True}
    assert set(eps_view) == {"enabled", "sandbox", "store_id", "username", "password", "hash_key"}
    stored = conn.execute(text("SELECT ciphertext FROM app_secrets WHERE name = 'eps.store_id'")).scalar_one()
    assert "S-1" not in stored
    from app.secrets_store import read_secret

    assert read_secret(conn, "eps.store_id") == "S-1"
    # A client that does not send EPS keeps it as it is.
    del body["gateways"]["eps"]
    assert client.put("/api/settings", json=body).json()["gateways"]["eps"]["enabled"] is True
    public = client.get("/api/settings/public").json()["gateways"]["eps"]
    assert set(public) == {"enabled", "sandbox"}


# b270
def test_b270_no_secrets_anywhere(
    client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    started = pay_eps(client, eps_world)
    payment = payment_row(conn, started.json()["payment_id"])
    fake_eps.status = success(payment, storeId=EPS_SECRETS["eps.store_id"], token=EPS_TOKEN,
                              ValueB=EPS_SECRETS["eps.password"])
    bodies = [started.text, back(client, payment, "success", f"?x-hash=abc&note={EPS_TOKEN}").text]
    for path in ("/api/admin/ledger", "/api/admin/invoices", "/api/settings", f"/api/me/payments/{payment['id']}"):
        bodies.append(client.get(path).text)
    events = json.dumps(conn.execute(text("SELECT detail FROM payment_events")).scalars().all())
    audit = json.dumps(conn.execute(text("SELECT detail FROM audit_log")).scalars().all())
    haystack = "\n".join(bodies) + events + audit + caplog.text
    hashes = [r.headers["x-hash"] for r in fake_eps.requests]
    for secret in (*EPS_SECRETS.values(), EPS_TOKEN, *hashes):
        assert secret not in haystack, secret


def test_one_audit_row_when_paid(client: TestClient, conn: Connection, eps_world: dict[str, Any], fake_eps: FakeEps) -> None:
    payment = payment_row(conn, pay_eps(client, eps_world).json()["payment_id"])
    fake_eps.status = success(payment)
    before = audit_count(conn)
    back(client, payment, "success")
    assert audit_count(conn) == before + 1
