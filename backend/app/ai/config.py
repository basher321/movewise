"""AI provider settings (spec B17): order, enabled and model in settings.ai; keys in app_secrets."""

import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.secrets_store import read_secret

Provider = Literal["claude", "openai", "gemini", "groq"]
# The failover order is fixed: Claude, then ChatGPT, then Gemini, then Groq.
PROVIDERS: tuple[Provider, ...] = ("claude", "openai", "gemini", "groq")
PROVIDER_LABELS: dict[Provider, str] = {"claude": "Claude", "openai": "ChatGPT", "gemini": "Gemini", "groq": "Groq"}
DEFAULT_MODELS: dict[Provider, str] = {"claude": "claude-opus-5-5", "openai": "", "gemini": "", "groq": ""}
MODEL_RE = re.compile(r"[A-Za-z0-9._:/-]{1,100}")
MAX_KEY = 500


def key_name(provider: Provider) -> str:
    return f"ai.{provider}_key"


@dataclass(frozen=True)
class ReadyProvider:
    provider: Provider
    model: str
    key: str


def default_ai() -> dict[str, Any]:
    return {
        "order": list(PROVIDERS),
        "providers": {p: {"enabled": False, "model": DEFAULT_MODELS[p]} for p in PROVIDERS},
    }


def normalise(raw: Any) -> dict[str, Any]:
    """The stored ai block, with anything missing or unknown replaced by the defaults."""
    out = default_ai()
    if not isinstance(raw, dict):
        return out
    # The order is always PROVIDERS (a different order saved before is not used).
    providers = raw.get("providers")
    if isinstance(providers, dict):
        for p in PROVIDERS:
            item = providers.get(p)
            if isinstance(item, dict):
                out["providers"][p]["enabled"] = item.get("enabled") is True
                model = item.get("model")
                if isinstance(model, str) and (model == "" or MODEL_RE.fullmatch(model)):
                    out["providers"][p]["model"] = model
    return out


def read_ai(conn: Connection) -> dict[str, Any]:
    raw = conn.execute(text("SELECT ai FROM settings WHERE singleton = 'settings'")).scalar_one()
    return normalise(raw)


def ready_providers(conn: Connection) -> list[ReadyProvider]:
    """Enabled providers with a model and a readable key, in the fixed order of PROVIDERS."""
    ai = read_ai(conn)
    ready = []
    for p in PROVIDERS:
        item = ai["providers"][p]
        if not item["enabled"] or not item["model"]:
            continue
        key = read_secret(conn, key_name(p))
        if key:
            ready.append(ReadyProvider(p, item["model"], key))
    return ready
