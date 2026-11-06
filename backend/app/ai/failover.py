"""Failover across the AI providers (spec B17): Claude, ChatGPT, Gemini, Groq in this fixed order;
the first usable answer wins. An answer that fails the check (numbers not in the database facts)
counts as a failure, so the next provider answers."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.ai import providers
from app.ai.config import Provider, ReadyProvider

logger = logging.getLogger("app.ai")


@dataclass(frozen=True)
class Answer:
    text: str
    provider: Provider


def first_answer(
    ready: list[ReadyProvider], system: str, user: str, check: Callable[[str], bool] | None = None
) -> Answer | None:
    for p in ready:
        result = providers.ask(p.provider, p.key, p.model, system, user)
        if result.ok and (check is None or check(result.text)):
            return Answer(result.text, p.provider)
        error = result.error if not result.ok else "answer not from the database facts"
        # Provider name and error code only: never the key, the prompt or the question.
        logger.warning("AI provider %s failed: %s", p.provider, error)
    return None
