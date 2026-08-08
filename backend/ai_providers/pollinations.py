"""Pollinations.ai — free, keyless chat completions, chat()'s second
tier (tried after Groq, before Hugging Face). `configured` is always
True: unlike Groq/HF, there's no required key gating this tier — an
optional POLLINATIONS_API_TOKEN only raises Pollinations' own rate
limit, it was never a precondition for attempting a call (see
config.py's pollinations_token field)."""

from __future__ import annotations

import logging

import httpx

from ..config import settings
from .base import AIProvider, post_with_retry

logger = logging.getLogger("lingua.ai_providers.pollinations")


class PollinationsProvider(AIProvider):
    name = "pollinations"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def configured(self) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.pollinations_token}"} if settings.pollinations_token else {}

    async def chat(self, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str | None:
        try:
            resp = await post_with_retry(
                self._http,
                settings.pollinations_chat_endpoint,
                headers=self._headers(),
                json={
                    "model": settings.chat_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            logger.warning("Pollinations chat HTTP %s: %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.warning("Pollinations chat failed: %s", e)
        return None
