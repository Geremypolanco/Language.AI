"""Lightweight, structured request-level logging for the tutor-conversation
turn — not a metrics platform, just clean JSON log lines through the
standard `logging` module, cheap enough to leave on in production.

Scoped to the one lifecycle that actually has multiple slow, independently-
measurable steps right now: a conversation turn (chat completion, then
per-sentence Piper/HF synthesis — see routers/conversation.py). A log line
here says *why* a turn was slow (chat vs. TTS, and how much text/audio it
was carrying), not just that it was.
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
