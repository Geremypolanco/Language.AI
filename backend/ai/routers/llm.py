"""LLM Router — the single entry point for text generation, dialogue, and
content-authoring calls in this app:

    Conversation -> LLM Router -> ideal model

Delegates to hf_client, which already implements the real provider chain
(Groq -> Pollinations -> Hugging Face) and its reliability engineering
(retries, circuit breakers, the shared HF budget guard — see
hf_client._HFGuard). This router's job is to be the one place the rest of
the app reaches for chat completions, not to reimplement logic that's
already production-proven. See backend/ai/registry.py's AITask.CHAT entry
for which model is actually selected at each tier and why."""

from __future__ import annotations

from typing import AsyncIterator

from ...hf_client import hf_client
from ..registry import AITask, chain_for


class LLMRouter:
    @property
    def active_chain(self):
        """The current provider chain for chat/content-authoring calls, in
        try-order — see backend/ai/registry.py."""
        return chain_for(AITask.CHAT)

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        return await hf_client.chat(messages, max_tokens=max_tokens, temperature=temperature)

    async def stream_chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = 1000, temperature: float = 0.7
    ) -> AsyncIterator[str]:
        async for chunk in hf_client.stream_chat(messages, max_tokens=max_tokens, temperature=temperature):
            yield chunk

    async def conversation_reply(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        return await hf_client.conversation_reply(system_prompt, history)
