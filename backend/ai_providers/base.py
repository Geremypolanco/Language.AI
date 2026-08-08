"""Contracts for the provider cascades extracted from HFClient (see
hf_client.py), one per modality — not designed from a blank page. Only
the methods each contract's real implementations actually use are here:
AIProvider.chat for the three chat providers, STTProvider.transcribe for
the two speech-to-text providers. No `health_check`/`models`-style
methods, since nothing in this app implements those today. The next
provider (whichever model/vendor that ends up being) implements whichever
of these contracts fits; nothing else in the app needs to change.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger("lingua.ai_providers")

# Same daily-circuit-breaker cooldown hf_client.py used before this moved —
# see HFGuard below. (Not the same value as ElevenLabs' separate 60s
# circuit breaker in hf_client.py — different tier, different constant.)
_CIRCUIT_COOLDOWN_S = 120.0


class AIProvider(ABC):
    """One chat-completion source in the cascade a caller (today, just
    HFClient.chat()) tries in order until one succeeds."""

    name: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        """Whether this provider has what it needs (an API key, etc.) to
        even attempt a call — checked before spending a network round trip
        on a provider that's certain to fail or be skipped."""

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str | None:
        """Returns the completion text, or None if this provider's call
        failed or was skipped (not configured, rate-limited, non-200,
        network error, ...). Never raises for an ordinary failure — the
        caller's whole point in trying a list of these is to fall through
        to the next one, so only a genuine bug in this method should
        raise out of it."""


class STTProvider(ABC):
    """One speech-to-text source in speech_to_text()'s cascade, tried in
    order until one returns a transcript. A separate contract from
    AIProvider, not a reuse of it — the input/output shape genuinely
    differs (audio bytes + content type in, transcript text out), not
    just the model being called."""

    name: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, content_type: str) -> str | None:
        """Returns the transcript — which may legitimately be "" (a real
        "nothing intelligible was said" result, not a signal to try the
        next provider) — or None if this provider's call failed or was
        skipped. Same never-raises-for-ordinary-failure contract as
        AIProvider.chat."""


# Flat per-call cost estimate for HF calls that aren't plain text-in/text-out
# (STT reads audio, video's cost isn't proportional to the prompt string) —
# picked so a handful of video generations (the heaviest call this app makes
# against HF) meaningfully draws down HFGuard's daily budget instead of
# registering as nearly free the way a short text prompt's char-count would.
# Shared between HFSTTProvider here and hf_client.py's still-unextracted
# text_to_speech()/generate_video(), which is why these live here rather
# than staying private to one module.
HF_AUDIO_CALL_COST = 500
HF_VIDEO_CALL_COST = 4000


async def post_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """One retry on a transient network failure (DNS blip, connection
    reset) before giving up — same policy hf_client.py's own
    _post_with_retry still applies to its other (TTS/image/video) calls,
    which stay on that private copy since they're out of scope here."""
    for attempt in range(2):
        try:
            return await client.post(url, **kwargs)
        except httpx.TransportError:
            if attempt == 1:
                raise
            await asyncio.sleep(0.5)
    raise AssertionError("unreachable")  # loop always returns or raises


class HFGuard:
    """Tracks whether it's currently safe to spend more Hugging Face
    quota. HF is the one AI tier in this app with a real credit-limited
    budget, and it's used as a last-resort fallback across several call
    sites (chat here, plus STT/TTS/video in hf_client.py) — one shared
    instance is passed to whichever of those need it, not recreated per
    call site. Not a real token-accurate meter (there's no tokenizer
    here, just chars/4 and flat per-modality estimates elsewhere); it
    only needs to be a safety margin, not a billing reconciliation."""

    def __init__(self, daily_budget: int, cooldown_s: float = _CIRCUIT_COOLDOWN_S) -> None:
        self._daily_budget = daily_budget
        self._cooldown_s = cooldown_s
        self._circuit_open_until = 0.0
        self._budget_day: str | None = None
        self._used_today = 0

    def _roll_window_if_new_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self._budget_day:
            self._budget_day = today
            self._used_today = 0

    def allowed(self) -> bool:
        if time.monotonic() < self._circuit_open_until:
            return False
        self._roll_window_if_new_day()
        return self._used_today < self._daily_budget

    def record_usage(self, units: int) -> None:
        self._roll_window_if_new_day()
        self._used_today += max(0, units)

    def record_rate_limited(self) -> None:
        self._circuit_open_until = time.monotonic() + self._cooldown_s
        logger.warning("Hugging Face rate-limited/budget exhausted — pausing that tier for %.0fs", self._cooldown_s)
