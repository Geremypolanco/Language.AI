"""Structured JSON telemetry for a student's conversational turn (LLM
generation + voice synthesis) — emitted through the standard logging module
so it composes with whatever log shipper/aggregator a real deployment
already runs, rather than inventing a bespoke sink or transport of its own.
One flat, machine-parseable JSON object per turn; nothing here buffers,
batches, or ships data anywhere by itself.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("lingua.telemetry")


@contextmanager
def measure_ms() -> Iterator[dict[str, float]]:
    """`with measure_ms() as timer: ...` — timer['duration_ms'] is set on
    exit, including when the block raises, so a failed call is still timed
    rather than silently dropped from the metric."""
    state: dict[str, float] = {}
    start = time.monotonic()
    try:
        yield state
    finally:
        state["duration_ms"] = round((time.monotonic() - start) * 1000, 2)


def log_student_turn(
    *,
    duration_ms: float,
    voice_tier_utilized: str,
    tokens_consumed: int | None,
    circuit_breaker_state: bool,
) -> None:
    """One JSON line per student turn (chat generation + voice synthesis).

    tokens_consumed is None — never a fabricated number — whenever the chat
    provider's response didn't include a `usage` block; not every
    OpenAI-compatible endpoint reliably sends one, and HFClient.chat() only
    sets it when the field is actually present (see hf_client.py)."""
    logger.info(
        json.dumps(
            {
                "event": "student_turn",
                "duration_ms": duration_ms,
                "voice_tier_utilized": voice_tier_utilized,
                "tokens_consumed": tokens_consumed,
                "circuit_breaker_state": circuit_breaker_state,
            }
        )
    )
