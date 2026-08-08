"""Groq — hosted Llama 3.1 70B, chat()'s primary tier (elite free speed
and quality, tried before Pollinations/Hugging Face). Needs GROQ_API_KEY;
unset means `configured` is False and the caller skips straight to the
next provider without a network call. Logic moved verbatim from
hf_client.py's old chat() body — see AIProvider for why this contract is
narrow."""

from __future__ import annotations

import logging

import httpx

from ..config import settings
from .base import AIProvider, post_with_retry

logger = logging.getLogger("lingua.ai_providers.groq")

_CHAT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_CHAT_MODEL = "llama-3.1-70b-versatile"


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def configured(self) -> bool:
        return bool(settings.groq_api_key)

    async def chat(self, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str | None:
        if not self.configured:
            return None
        try:
            resp = await post_with_retry(
                self._http,
                _CHAT_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": _CHAT_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            logger.warning("Groq chat HTTP %s: %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.warning("Groq chat failed: %s", e)
        return None
