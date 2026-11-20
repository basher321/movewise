"""AI calls of the CV Agent (spec B28 section 3).

Uses the providers and keys already set up in Settings (B17), in the same fixed failover order.
Every call asks for strict JSON, checks it with a Pydantic model and retries once with the same
provider when the JSON is invalid; then the next provider is tried. Images (scans, photos) go
only to providers that can read them (Claude, ChatGPT, Gemini). Each attempt is counted in
cv_ai_calls (service, provider, status, tokens) - never the prompt, the documents or the answer.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.ai import providers
from app.ai.config import Provider, ReadyProvider, ready_providers
from app.config import BACKEND_DIR
from app.errors import ApiError

logger = logging.getLogger("app.ai")

PROMPTS_DIR = BACKEND_DIR / "prompts" / "cv"
TIMEOUT_SECONDS = 90.0
MAX_OUTPUT_TOKENS = 8000
VISION: tuple[Provider, ...] = ("claude", "openai", "gemini")
JSON_REMINDER = (
    "\n\nYour previous answer was not valid JSON for the required shape. Answer again with ONLY one JSON "
    "object, no code fences, no text before or after it."
)

M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True)
class Image:
    mime: str
    data: bytes


@dataclass(frozen=True)
class Caller:
    """Who the call is for: the CV project and the applicant (for counting and the daily limit)."""

    project_id: Any
    applicant_id: Any


def prompt(name: str) -> str:
    """A prompt file from backend/prompts/cv/, read on every call so edits apply at once.
    {{rules}} inside it is replaced by rules.md (the non-negotiable writing rules)."""
    body = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    if "{{rules}}" in body:
        body = body.replace("{{rules}}", (PROMPTS_DIR / "rules.md").read_text(encoding="utf-8"))
    return body


def ensure_allowance(conn: Connection, caller: Caller, calls: int = 1) -> None:
    limit = int(conn.execute(text("SELECT cv_ai_per_day FROM settings WHERE singleton = 'settings'")).scalar_one())
    used = conn.execute(
        text("SELECT count(*) FROM cv_ai_calls WHERE applicant_id = :a AND created_at > now() - interval '24 hours'"),
        {"a": caller.applicant_id},
    ).scalar_one()
    if int(used) + calls > limit:
        raise ApiError(
            "TOO_MANY_TRIES", 429,
            f"You have used today's {limit} AI actions. Please continue tomorrow; your CV is saved.",
        )


def _record(conn: Connection, caller: Caller, service: str, provider: str | None, status: str, usage: tuple[int | None, int | None]) -> None:
    conn.execute(
        text(
            "INSERT INTO cv_ai_calls (project_id, applicant_id, service, provider, status, input_tokens, output_tokens) "
            "VALUES (:p, :a, :s, :pr, :st, :i, :o)"
        ),
        {"p": caller.project_id, "a": caller.applicant_id, "s": service, "pr": provider, "st": status,
         "i": usage[0], "o": usage[1]},
    )


def _with_images(provider: Provider, body: dict[str, Any], user: str, images: list[Image]) -> None:
    encoded = [(i.mime, base64.b64encode(i.data).decode("ascii")) for i in images]
    if provider == "claude":
        blocks: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": m, "data": d}} for m, d in encoded
        ]
        body["messages"][0]["content"] = blocks + [{"type": "text", "text": user}]
    elif provider == "openai":
        parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
        parts += [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{d}"}} for m, d in encoded]
        body["messages"][1]["content"] = parts
    elif provider == "gemini":
        body["contents"][0]["parts"] = [{"text": user}] + [{"inline_data": {"mime_type": m, "data": d}} for m, d in encoded]


def build(provider: Provider, key: str, model: str, system: str, user: str, images: list[Image]) -> providers.Request:
    url, headers, body = providers.build_request(provider, key, model, system, user)
    if provider == "claude":
        body["max_tokens"] = MAX_OUTPUT_TOKENS
    elif provider in ("openai", "groq"):
        body["max_completion_tokens"] = MAX_OUTPUT_TOKENS
        body["response_format"] = {"type": "json_object"}
    else:
        body["generationConfig"] = {"maxOutputTokens": MAX_OUTPUT_TOKENS, "responseMimeType": "application/json"}
    if images:
        _with_images(provider, body, user, images)
    return url, headers, body


def _usage(provider: Provider, data: Any) -> tuple[int | None, int | None]:
    if not isinstance(data, dict):
        return None, None
    if provider == "claude":
        u = data.get("usage") or {}
        return u.get("input_tokens"), u.get("output_tokens")
    if provider in ("openai", "groq"):
        u = data.get("usage") or {}
        return u.get("prompt_tokens"), u.get("completion_tokens")
    u = data.get("usageMetadata") or {}
    return u.get("promptTokenCount"), u.get("candidatesTokenCount")


def _send(p: ReadyProvider, system: str, user: str, images: list[Image]) -> tuple[str, str, tuple[int | None, int | None]]:
    """(text, error, usage) for one request."""
    url, headers, body = build(p.provider, p.key, p.model, system, user, images)
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=providers.TRANSPORT) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        return "", "timeout", (None, None)
    except httpx.HTTPError as exc:
        return "", type(exc).__name__, (None, None)
    if response.status_code >= 400:
        return "", f"HTTP {response.status_code}", (None, None)
    try:
        data = response.json()
    except ValueError:
        return "", "unreadable reply", (None, None)
    answer, error = providers.answer_text(p.provider, data)
    return answer, error, _usage(p.provider, data)


def parse_json(answer: str, model: type[M]) -> M | None:
    raw = answer.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return model.model_validate(json.loads(raw[start : end + 1]))
    except (ValueError, ValidationError):
        return None


class AiUnavailable(ApiError):
    def __init__(self) -> None:
        super().__init__("INTERNAL", 500, "The AI assistant could not answer just now. Please try again in a minute.")


def ask_json(
    conn: Connection,
    caller: Caller,
    service: str,
    system: str,
    user: str,
    model: type[M],
    images: list[Image] | None = None,
) -> M:
    """The first valid answer, provider by provider. Raises AiUnavailable when none answers."""
    ensure_allowance(conn, caller)
    ready = ready_providers(conn)
    if images:
        ready = [p for p in ready if p.provider in VISION]
    if not ready:
        raise ApiError("INTERNAL", 500, "The AI assistant is not set up yet. Please contact us.")
    for p in ready:
        for attempt in (0, 1):
            answer, error, usage = _send(p, system, user + (JSON_REMINDER if attempt else ""), images or [])
            if not answer:
                _record(conn, caller, service, p.provider, "failed", usage)
                logger.warning("CV AI %s failed at %s: %s", service, p.provider, error or "empty")
                break
            parsed = parse_json(answer, model)
            if parsed is not None:
                _record(conn, caller, service, p.provider, "ok", usage)
                return parsed
            _record(conn, caller, service, p.provider, "invalid_json", usage)
            logger.warning("CV AI %s gave invalid JSON at %s (attempt %d)", service, p.provider, attempt + 1)
    raise AiUnavailable()


def prompt_files() -> list[Path]:
    return sorted(PROMPTS_DIR.glob("*.md"))
