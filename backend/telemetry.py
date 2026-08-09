"""Lightweight, structured request-level logging — not a metrics platform,
just clean JSON log lines through the standard `logging` module, cheap
enough to leave on in production.

Two independent things get logged here:

1. The tutor-conversation turn (chat completion, then per-sentence Piper/
   HF synthesis — see routers/conversation.py): log_tutor_turn says *why*
   a turn was slow (chat vs. TTS, how much text/audio it carried), not
   just that it was.
2. Provider-cascade resolution (HFClient.chat()/speech_to_text(), see
   hf_client.py and backend/ai_providers/): log_provider_resolution/
   log_provider_exhausted say *which* provider actually served a call and
   whether it took more than one attempt. Deliberately narrow — provider
   name, attempt number, fallback, latency; no cost or "quality" field,
   since neither has a real data source in this app (free-tier providers
   with no per-call cost API, and no human eval/user feedback loop to
   grade a reply's quality against). Each provider's own failure reason
   (HTTP status, exception) is already logged where it happens, in
   backend/ai_providers/*.py — these two functions log the aggregate
   outcome of a whole cascade, not a duplicate of that per-attempt detail.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("lingua.telemetry")


@contextmanager
def timed(box: dict) -> Iterator[None]:
    """Fills box["elapsed_ms"] with the wall-clock duration of the `with`
    block, in milliseconds. Takes the dict as a parameter (rather than
    yielding one) so a caller can pass an existing dict and read the result
    after the block exits, without needing a second variable."""
    start = time.perf_counter()
    try:
        yield
    finally:
        box["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)


def log_tutor_turn(
    *,
    user_id: str,
    chat_ms: float,
    tts_ms: float,
    chars_in: int,
    chars_out: int,
    sentence_count: int,
) -> None:
    """One JSON line per tutor-conversation turn (see
    routers/conversation.py's WebSocket loop) — chat_ms/tts_ms are the two
    steps that dominate perceived latency; chars_in/out and sentence_count
    give enough context to tell "slow because the reply was long" apart
    from "slow because a provider was slow" just by reading the log."""
    logger.info(
        json.dumps(
            {
                "event": "tutor_turn",
                "user_id": user_id,
                "chat_ms": chat_ms,
                "tts_ms": tts_ms,
                "total_ms": round(chat_ms + tts_ms, 1),
                "chars_in": chars_in,
                "chars_out": chars_out,
                "sentence_count": sentence_count,
            }
        )
    )


def log_provider_resolution(*, capability: str, provider: str, attempt: int, elapsed_ms: float) -> None:
    """One JSON line each time a provider cascade (chat or stt) resolves —
    which provider served it, whether that took more than one attempt
    (fallback), and how long that provider's own call took. `attempt` is
    1-indexed position in the cascade (backend/ai_providers/), so
    `fallback` is just `attempt > 1` rather than a second thing to keep
    in sync."""
    logger.info(
        json.dumps(
            {
                "event": "provider_resolution",
                "capability": capability,
                "provider": provider,
                "attempt": attempt,
                "fallback": attempt > 1,
                "elapsed_ms": elapsed_ms,
            }
        )
    )


def log_provider_exhausted(*, capability: str, providers_tried: int) -> None:
    """One JSON line when every provider in a cascade failed — the
    complement to log_provider_resolution, so a total-outage window shows
    up in the same log stream instead of only ever seeing successes."""
    logger.warning(
        json.dumps({"event": "provider_exhausted", "capability": capability, "providers_tried": providers_tried})
    )
