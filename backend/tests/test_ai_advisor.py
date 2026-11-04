"""B17: AI advisors, provider settings, failover and the test endpoint (b139-b145).

No test ever calls a real provider: providers.TRANSPORT is replaced by a fake httpx transport.
"""

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.ai import providers
from auth_helpers import license_modules
from conftest import new_client
from test_catalog import university_body, vacancy_body

KEYS = {"claude": "sk-claude-secret-111", "openai": "sk-openai-secret-222", "gemini": "gm-secret-333", "groq": "gq-secret-444"}
ALL = ("course", "study", "job")


class FakeProviders:
    """Answers per host: a status code and a reply text. Records every request."""

    def __init__(self) -> None:
        self.status: dict[str, int] = {}
        self.reply: dict[str, str] = {}
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        host = request.url.host
        name = {"api.anthropic.com": "claude", "api.openai.com": "openai", "generativelanguage.googleapis.com": "gemini", "api.groq.com": "groq"}[host]
        status = self.status.get(name, 200)
        if status == -1:
            raise httpx.ConnectTimeout("timed out", request=request)
        if status >= 400:
            return httpx.Response(status, json={"error": {"message": "nope " + KEYS[name]}})
        text_reply = self.reply.get(name, f"Answer from {name}")
        if name == "claude":
            return httpx.Response(200, json={"content": [{"type": "text", "text": text_reply}], "stop_reason": "end_turn"})
        if name == "gemini":
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text_reply}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": text_reply}}]})

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(c.content) for c in self.calls]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeProviders]:
    f = FakeProviders()
    monkeypatch.setattr(providers, "TRANSPORT", httpx.MockTransport(f.handler))
    yield f


def ai_block(enabled: tuple[str, ...] = (), order: list[str] | None = None, keys: bool = True, **models: str) -> dict[str, Any]:
    defaults = {"claude": "claude-opus-5-5", "openai": "gpt-test", "gemini": "gemini-test", "groq": "llama-test"}
    defaults.update(models)
    return {
        "order": order or ["claude", "openai", "gemini", "groq"],
        "providers": {
            p: {"enabled": p in enabled, "model": defaults[p], "key": KEYS[p] if keys else ""} for p in defaults
        },
    }


@pytest.fixture
def setup(client: TestClient, conn: Connection, act_as: Callable[..., Any], settings_body: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    license_modules(conn, *ALL)
    act_as("super_admin")
    uni = client.post(
        "/api/admin/universities",
        json=university_body(name="Maple Ridge University", country="Canada", admissions_email="secret-admissions@example.test"),
    ).json()
    hidden = client.post("/api/admin/universities", json=university_body(name="Hidden Draft College", country="Canada", published=False))
    assert hidden.status_code == 200, hidden.text
    vac = client.post("/api/admin/vacancies", json=vacancy_body(employer_email="boss@example.test")).json()
    body = settings_body(phone="+880 1700-000000", email="hello@agency.example", name="Test Agency")
    return {"uni": uni, "vac": vac, "body": body}


def save_ai(client: TestClient, body: dict[str, Any], ai: dict[str, Any]) -> httpx.Response:
    return client.put("/api/settings", json={**body, "ai": ai})


def ask(client: TestClient, module: str, question: str, inputs: dict[str, Any] | None = None) -> httpx.Response:
    return client.post(f"/api/agent/{module}/ask", json={"question": question, "inputs": inputs})


# b139
def test_b139_settings_show_key_status_only(client: TestClient, conn: Connection, setup: dict[str, Any]) -> None:
    before = client.get("/api/settings").json()["ai"]
    assert before["order"] == ["claude", "openai", "gemini", "groq"]
    assert before["providers"]["claude"] == {"enabled": False, "model": "claude-opus-5-5", "key": {"saved": False}}
    saved = save_ai(client, setup["body"], ai_block(("claude", "groq"), order=["groq", "claude", "openai", "gemini"]))
    assert saved.status_code == 200, saved.text
    ai = saved.json()["ai"]
    assert ai["order"][0] == "groq"
    assert all(ai["providers"][p]["key"] == {"saved": True} for p in KEYS)
    raw = json.dumps(saved.json())
    for key in KEYS.values():
        assert key not in raw
    cipher = conn.execute(text("SELECT string_agg(ciphertext, '') FROM app_secrets WHERE name LIKE 'ai.%'")).scalar_one()
    assert cipher and all(k not in cipher for k in KEYS.values())
    detail = conn.execute(text("SELECT detail FROM audit_log WHERE action = 'settings.saved' ORDER BY at DESC LIMIT 1")).scalar_one()
    assert "ai.claude_key" in detail and all(k not in detail for k in KEYS.values())
    # An empty key keeps the saved one.
    again = save_ai(client, setup["body"], ai_block(("claude",), keys=False))
    assert again.status_code == 200 and again.json()["ai"]["providers"]["claude"]["key"] == {"saved": True}
    # A body without ai keeps the AI settings.
    plain = client.put("/api/settings", json=setup["body"])
    assert plain.status_code == 200 and plain.json()["ai"]["providers"]["claude"]["enabled"] is True
    public = client.get("/api/settings/public").json()
    assert "ai" not in public


# b140
@pytest.mark.parametrize(
    "ai",
    [
        ai_block(("claude",), keys=False),
        ai_block(("openai",), openai=""),
        ai_block(order=["claude", "claude", "gemini", "groq"]),
        ai_block(order=["claude", "openai", "gemini"]),
        ai_block(("claude",), claude="bad model name!"),
        {"order": ["claude", "openai", "gemini", "groq"], "providers": {"claude": {"enabled": True, "model": "x", "key": "k"}}},
        {"order": ["claude", "openai", "gemini", "groq"], "providers": {p: {"enabled": "yes", "model": "x"} for p in KEYS}},
    ],
)
def test_b140_invalid_ai_settings(client: TestClient, conn: Connection, setup: dict[str, Any], ai: dict[str, Any]) -> None:
    before = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
    response = save_ai(client, setup["body"], ai)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION", response.text
    assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == before


# b141
def test_b141_failover_and_rule_based_fallback(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("claude", "openai", "gemini", "groq")))
    assert ask(client, "study", "What does Maple Ridge cost?").json()["answer"] == "Answer from claude"
    fake.status["claude"] = 500
    assert ask(client, "study", "What does Maple Ridge cost?").json()["answer"] == "Answer from openai"
    fake.status["openai"] = 429
    fake.status["gemini"] = -1
    assert ask(client, "study", "What does Maple Ridge cost?").json()["answer"] == "Answer from groq"
    fake.status["groq"] = 401
    rule = ask(client, "study", "What does Maple Ridge cost?").json()["answer"]
    assert rule.startswith("Please fill in the form first")
    fake.status = {}
    fake.reply["claude"] = "   "
    assert ask(client, "study", "Hello").json()["answer"] == "Answer from openai"  # empty reply moves on


def test_claude_request_shape(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("claude",)))
    ask(client, "study", "Hi")
    request = fake.calls[-1]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEYS["claude"]
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert request.headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    body = fake.bodies()[-1]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "low"}
    assert "temperature" not in body and "thinking" not in body
    refused = {"content": [], "stop_reason": "refusal"}
    assert providers.answer_text("claude", refused) == ("", "declined")


# b142
def test_b142_prompt_has_only_public_facts(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("claude",)))
    ask(client, "study", "Tell me about Canada", {"level": "Bachelor", "gpa": 3.5})
    body = fake.bodies()[-1]
    prompt = body["system"] + body["messages"][0]["content"]
    assert "Maple Ridge University" in prompt
    assert "Hidden Draft College" not in prompt
    assert "secret-admissions@example.test" not in prompt
    assert "apply_link" not in prompt and "Site Supervisor" not in prompt  # nothing from Job Processing
    assert "+880 1700-000000" in prompt and "hello@agency.example" in prompt and "Test Agency" in prompt
    assert "Never invent" in body["system"]
    facts = json.loads(body["messages"][0]["content"].split("FACTS (JSON):\n", 1)[1].split("\n\nVISITOR FORM INPUTS", 1)[0])
    assert facts["items_match_the_question"] is True and facts["process_stages"]
    assert facts["universities"][0]["our_application_fee"].startswith("৳")


def test_closed_vacancy_not_in_prompt(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    closed = client.post("/api/admin/vacancies", json=vacancy_body(title="Closed Welder Role", closed=True))
    assert closed.status_code == 200, closed.text
    save_ai(client, setup["body"], ai_block(("openai",)))
    ask(client, "job", "Any welder jobs?")
    body = fake.bodies()[-1]
    content = body["messages"][1]["content"]
    assert "Closed Welder Role" not in content and "boss@example.test" not in content
    assert body["messages"][0]["role"] == "system"


# b143
def test_b143_no_match_still_has_contact_and_rule(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("gemini",)))
    ask(client, "study", "Do you have universities in Antarctica?")
    body = fake.bodies()[-1]
    content = body["contents"][0]["parts"][0]["text"]
    facts = json.loads(content.split("FACTS (JSON):\n", 1)[1].split("\n\nVISITOR FORM INPUTS", 1)[0])
    assert facts["items_match_the_question"] is False
    assert facts["company"]["phone"] == "+880 1700-000000"
    assert "do not have that information" in body["systemInstruction"]["parts"][0]["text"]
    assert fake.calls[-1].headers["x-goog-api-key"] == KEYS["gemini"]
    assert "gemini-test:generateContent" in str(fake.calls[-1].url)


# b144
def test_b144_test_endpoint(api: FastAPI, client: TestClient, conn: Connection, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("claude",)))
    assert client.post("/api/admin/settings/test-ai", json={"provider": "claude"}).json() == {"ok": True}
    fake.status["claude"] = 401
    failed = client.post("/api/admin/settings/test-ai", json={"provider": "claude"}).json()
    assert failed["ok"] is False and "401" in failed["error"] and KEYS["claude"] not in json.dumps(failed)
    no_key = client.post("/api/admin/settings/test-ai", json={"provider": "openai"}).json()
    assert no_key == {"ok": True}  # saved key and model, the fake answers
    assert client.post("/api/admin/settings/test-ai", json={"provider": "other"}).json()["code"] == "VALIDATION"
    admin = new_client(api)
    from auth_helpers import sign_in_admin_on

    sign_in_admin_on(admin, conn, "admin", ["study"])
    assert admin.post("/api/admin/settings/test-ai", json={"provider": "claude"}).json()["code"] == "FORBIDDEN"
    anon = new_client(api)
    anon.cookies.clear()
    assert anon.post("/api/admin/settings/test-ai", json={"provider": "claude"}).status_code == 401


def test_test_endpoint_without_key(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    result = client.post("/api/admin/settings/test-ai", json={"provider": "groq"}).json()
    assert result["ok"] is False and "needs a saved model and API key" in result["error"]
    assert not fake.calls


# b145
def test_b145_rate_limit_and_licence(client: TestClient, conn: Connection, setup: dict[str, Any], fake: FakeProviders) -> None:
    save_ai(client, setup["body"], ai_block(("claude",)))
    for _ in range(20):
        assert ask(client, "study", "Hi").status_code == 200
    limited = ask(client, "study", "Hi")
    assert limited.status_code == 429 and limited.json()["code"] == "TOO_MANY_TRIES"
    assert len(fake.calls) == 20
    license_modules(conn, "course", "study")
    calls = len(fake.calls)
    response = ask(client, "job", "Hi")
    assert response.status_code == 403 and response.json()["code"] == "MODULE_NOT_LICENSED"
    assert len(fake.calls) == calls


def test_question_rules(client: TestClient, setup: dict[str, Any], fake: FakeProviders) -> None:
    assert ask(client, "study", "   ").json()["code"] == "VALIDATION"
    assert ask(client, "study", "x" * 501).json()["code"] == "VALIDATION"
    assert ask(client, "course", "hi").status_code == 404
    # No provider set up: the rule-based reply, and no provider is called.
    assert ask(client, "study", "hi").json()["answer"].startswith("Please fill in the form first")
    assert not fake.calls


def test_keys_never_logged(client: TestClient, setup: dict[str, Any], fake: FakeProviders, caplog: pytest.LogCaptureFixture) -> None:
    save_ai(client, setup["body"], ai_block(("claude", "openai")))
    fake.status["claude"] = 500
    fake.status["openai"] = 500
    with caplog.at_level("DEBUG"):
        ask(client, "study", "What is the fee?")
    logged = caplog.text
    assert "AI provider claude failed: HTTP 500" in logged
    assert all(k not in logged for k in KEYS.values()) and "What is the fee?" not in logged


def test_parallel_ai_cap_falls_back(client: TestClient, setup: dict[str, Any], fake: FakeProviders, monkeypatch: pytest.MonkeyPatch) -> None:
    """When every AI slot is busy, the question gets the rule-based reply at once (no provider call)."""
    import threading

    from app.ai import advisor

    save_ai(client, setup["body"], ai_block(("claude",)))
    monkeypatch.setattr(advisor, "_ai_slots", threading.BoundedSemaphore(1))
    assert advisor._ai_slots.acquire(blocking=False)
    try:
        assert ask(client, "study", "Hi").json()["answer"].startswith("Please fill in the form first")
        assert not fake.calls
    finally:
        advisor._ai_slots.release()
    assert ask(client, "study", "Hi").json()["answer"] == "Answer from claude"


def test_in_process_limit_without_log(client: TestClient, setup: dict[str, Any]) -> None:
    from app.ai import advisor

    for _ in range(advisor.RATE_LIMIT):
        assert advisor._reserve("198.51.100.7")
    assert not advisor._reserve("198.51.100.7")
    assert advisor._reserve("198.51.100.8")
