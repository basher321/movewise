"""Failover across the AI providers (spec B17): the saved order, the first usable answer wins."""

import logging
from dataclasses import dataclass

from app.ai import providers
from app.ai.config import Provider, ReadyProvider

logger = logging.getLogger("app.ai")


@dataclass(frozen=True)
class Answer:
    text: str
    provider: Provider


def first_answer(ready: list[ReadyProvider], system: str, user: str) -> Answer | None:
    for p in ready:
        result = providers.ask(p.provider, p.key, p.model, system, user)
        if result.ok:
            return Answer(result.text, p.provider)
        # Provider name and error code only: never the key, the prompt or the question.
        logger.warning("AI provider %s failed: %s", p.provider, result.error)
    return None
