"""Hugging Face — chat()'s and speech_to_text()'s last-resort tier (tried
after Groq, and after Pollinations for chat), paid/credit-limited (see
config.py's daily-budget rationale). Gated by an HFGuard circuit breaker/
budget shared across every HF call this app makes, not private to these
providers — the TTS/video call sites in hf_client.py (still out of scope
for this refactor, per the extraction audit) use the same guard instance,
so it's injected rather than owned here."""

from __future__ import annotations

import logging

import httpx

from ..config import settings
from .base import AIProvider, HFGuard, HF_AUDIO_CALL_COST, STTProvider, post_with_retry

logger = logging.getLogger("lingua.ai_providers.huggingface")


class HFProvider(AIProvider):
    name = "huggingface"

    def __init__(self, http: httpx.AsyncClient, hf_guard: HFGuard) -> None:
        self._http = http
        self._hf_guard = hf_guard

    @property
    def configured(self) -> bool:
        return settings.hf_configured

    async def chat(self, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str | None:
        if not (self.configured and self._hf_guard.allowed()):
            return None
        try:
            resp = await post_with_retry(
                self._http,
                settings.hf_chat_endpoint,
                headers={"Authorization": f"Bearer {settings.hf_token}"},
                json={
                    "model": settings.hf_chat_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                self._hf_guard.record_usage((sum(len(m.get("content", "")) for m in messages) + len(content)) // 4)
                return content
            if resp.status_code in (402, 429):
                self._hf_guard.record_rate_limited()
        except Exception as e:
            logger.warning("Hugging Face chat failed: %s", e)
        return None


class HFSTTProvider(STTProvider):
    name = "huggingface"

    def __init__(self, http: httpx.AsyncClient, hf_guard: HFGuard) -> None:
        self._http = http
        self._hf_guard = hf_guard

    @property
    def configured(self) -> bool:
        return settings.hf_configured

    async def transcribe(self, audio_bytes: bytes, content_type: str) -> str | None:
        if not (self.configured and self._hf_guard.allowed()):
            return None
        try:
            resp = await post_with_retry(
                self._http,
                f"{settings.hf_models_endpoint}/{settings.stt_model}",
                headers={"Authorization": f"Bearer {settings.hf_token}", "Content-Type": content_type},
                content=audio_bytes,
            )
            if resp.status_code == 200:
                self._hf_guard.record_usage(HF_AUDIO_CALL_COST)
                return resp.json().get("text", "").strip()
            if resp.status_code in (402, 429):
                self._hf_guard.record_rate_limited()
        except Exception as e:
            logger.warning("Hugging Face STT failed: %s", e)
        return None
