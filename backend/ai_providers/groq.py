"""Groq — hosted Llama 3.1 70B for chat, hosted Whisper for speech-to-text.
Both are chat()'s/speech_to_text()'s primary tier (elite free speed and
quality, tried before Pollinations/Hugging Face). Needs GROQ_API_KEY;
unset means `configured` is False and the caller skips straight to the
next provider without a network call. Logic moved verbatim from
hf_client.py's old chat()/speech_to_text() bodies — see AIProvider/
STTProvider for why each contract is narrow."""

from __future__ import annotations

import logging

import httpx

from ..config import settings
from .base import AIProvider, STTProvider, post_with_retry

logger = logging.getLogger("lingua.ai_providers.groq")

_CHAT_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_CHAT_MODEL = "llama-3.1-70b-versatile"
_STT_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
_STT_MODEL = "whisper-large-v3"


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


class GroqSTTProvider(STTProvider):
    name = "groq"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @property
    def configured(self) -> bool:
        return bool(settings.groq_api_key)

    async def transcribe(self, audio_bytes: bytes, content_type: str) -> str | None:
        if not self.configured:
            return None
        try:
            # Groq requires multipart/form-data for transcriptions — not a
            # JSON body like chat, so this doesn't share GroqProvider.chat's
            # request shape despite hitting the same host. No post_with_retry
            # here: the original speech_to_text() never wrapped this
            # particular call in a retry either (only its HF tier did) —
            # preserved as-is rather than silently changing retry behavior
            # during the move.
            files = {"file": ("audio.webm", audio_bytes, content_type), "model": (None, _STT_MODEL)}
            resp = await self._http.post(
                _STT_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files=files,
                timeout=30.0,
            )
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            logger.warning("Groq STT HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Groq STT failed: %s", e)
        return None
