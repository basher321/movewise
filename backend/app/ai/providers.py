"""One small HTTP client per AI provider (spec B17), with httpx (no extra packages).

- Claude: Anthropic Messages API, POST https://api.anthropic.com/v1/messages, headers x-api-key and
  anthropic-version 2026-10-21. For the current Claude models the server-side refusal fallback is
  on (anthropic-beta server-side-fallback-2026-07-01, "fallbacks": "default"); a final refusal
  still counts as a failure, so the next provider answers.
- ChatGPT: OpenAI Chat Completions, POST https://api.openai.com/v1/chat/completions.
- Gemini: POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent
  with the x-goog-api-key header.
- Groq: OpenAI-compatible Chat Completions, POST https://api.groq.com/openai/v1/chat/completions.

Keys go only in request headers and are never logged; error texts never contain them.
Tests set TRANSPORT to a fake transport, so no real provider is ever called from a test.
"""

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.ai.config import Provider

TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_TOKENS = 4000
TRANSPORT: httpx.BaseTransport | None = None

ANTHROPIC_VERSION = "2026-10-21"
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"
CLAUDE_FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"})
# Thinking cannot be switched off on the current Claude models; low effort keeps chat answers quick.
CLAUDE_EFFORT_MODELS = frozenset(
    {
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-haiku-5-5",
        "claude-fable-5-1",
        "claude-fable-5",
    }
)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    text: str = ""
    error: str = ""


Request = tuple[str, dict[str, str], dict[str, Any]]


def _claude(key: str, model: str, system: str, user: str) -> Request:
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if model in CLAUDE_EFFORT_MODELS:
        body["output_config"] = {"effort": "low"}
    if model in CLAUDE_FALLBACK_MODELS:
        headers["anthropic-beta"] = CLAUDE_FALLBACK_BETA
        body["fallbacks"] = "default"
    return CLAUDE_URL, headers, body


def _chat_completions(url: str, key: str, model: str, system: str, user: str) -> Request:
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    body = {
        "model": model,
        "max_completion_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    return url, headers, body


def _gemini(key: str, model: str, system: str, user: str) -> Request:
    headers = {"x-goog-api-key": key, "content-type": "application/json"}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    return GEMINI_URL.format(model=quote(model, safe="")), headers, body


def build_request(provider: Provider, key: str, model: str, system: str, user: str) -> Request:
    if provider == "claude":
        return _claude(key, model, system, user)
    if provider == "openai":
        return _chat_completions(OPENAI_URL, key, model, system, user)
    if provider == "groq":
        return _chat_completions(GROQ_URL, key, model, system, user)
    return _gemini(key, model, system, user)


def answer_text(provider: Provider, data: Any) -> tuple[str, str]:
    """(answer text, error). An empty text means the reply cannot be used."""
    if not isinstance(data, dict):
        return "", "unreadable reply"
    if provider == "claude":
        if data.get("stop_reason") == "refusal":
            return "", "declined"
        blocks = data.get("content") or []
        parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        return "".join(p for p in parts if isinstance(p, str)).strip(), ""
    if provider in ("openai", "groq"):
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return "", "no answer"
        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            return "", "no answer"
        if message.get("refusal"):
            return "", "declined"
        content = message.get("content")
        return (content.strip() if isinstance(content, str) else ""), ""
    candidates = data.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return "", "no answer"
    content = candidates[0].get("content") or {}
    parts = (content.get("parts") or []) if isinstance(content, dict) else []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    return "".join(t for t in texts if isinstance(t, str)).strip(), ""


def ask(provider: Provider, key: str, model: str, system: str, user: str) -> ProviderResult:
    url, headers, body = build_request(provider, key, model, system, user)
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=TRANSPORT) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        return ProviderResult(ok=False, error="timeout")
    except httpx.HTTPError as exc:
        return ProviderResult(ok=False, error=type(exc).__name__)
    if response.status_code >= 400:
        return ProviderResult(ok=False, error=f"HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        return ProviderResult(ok=False, error="unreadable reply")
    text, error = answer_text(provider, data)
    if not text:
        return ProviderResult(ok=False, error=error or "empty reply")
    return ProviderResult(ok=True, text=text)
