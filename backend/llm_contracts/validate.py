"""validate_or_retry — anti-hallucination enforcement with controlled degradation.

Every structured LLM output goes through this gate before it can reach a
learner:

  1. Call fn() to obtain a candidate result (raw JSON-decoded data).
  2. Validate it against the pydantic contract (a TypeAdapter).
  3. If it fails, wait (exponential backoff) and retry — up to 3 attempts.
  4. If it still fails, push a DeadLetterEntry to the queue and return
     (False, None). The output is quarantined, NEVER invented, padded, or
     silently coerced. The caller falls back to its own honest degraded
     path (offline content, fail-closed grade, …).

A fn() that RAISES (provider down, timeout, …) counts as a failed
attempt, exactly like an invalid payload — both mean "no trustworthy
output this round".
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, TypeVar, Union

from pydantic import BaseModel, TypeAdapter, ValidationError

from .dead_letter import DeadLetterEntry, DeadLetterQueue, dead_letters

logger = logging.getLogger("lingua.llm_contracts")

T = TypeVar("T")

# A contract is either a TypeAdapter (for lists / root models) or a plain
# BaseModel subclass.
Contract = Union[TypeAdapter[T], "type[BaseModel]"]


def _as_adapter(schema: Contract[T]) -> TypeAdapter[T]:
    if isinstance(schema, TypeAdapter):
        return schema
    return TypeAdapter(schema)


def _describe_errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        path = ".".join(str(p) for p in loc) if loc else "(root)"
        out.append(f"{path}: {err.get('msg', 'invalid')}")
    return out


async def validate_or_retry(
    fn: Callable[[], Any],
    schema: Contract[T],
    *,
    max_retries: int = 3,
    base_delay_s: float = 0.5,
    schema_name: str = "unknown",
    context: dict | None = None,
    queue: DeadLetterQueue | None = None,
) -> tuple[bool, T | None]:
    """Returns (True, data) when a candidate validated, else (False, None)
    after pushing a dead-letter entry. Never raises for validation
    problems; never fabricates data."""
    adapter = _as_adapter(schema)
    max_attempts = max(1, max_retries)
    base_delay_s = max(0.0, base_delay_s)
    q = queue if queue is not None else dead_letters
    ctx = dict(context or {})

    attempts = 0
    last_errors: list[str] = ["no attempts were made"]

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            candidate = fn()
            if inspect.isawaitable(candidate):
                candidate = await candidate
        except Exception as exc:  # provider failure, timeout, JSON error, …
            last_errors = [f"fetch raised {type(exc).__name__}: {exc}"]
        else:
            try:
                return True, adapter.validate_python(candidate)
            except ValidationError as exc:
                last_errors = _describe_errors(exc)

        if attempt < max_attempts and base_delay_s > 0:
            await asyncio.sleep(base_delay_s * (2 ** (attempt - 1)))

    entry = DeadLetterEntry.new(
        schema=schema_name,
        errors=last_errors,
        attempts=attempts,
        context=ctx,
    )
    q.push(entry)
    logger.warning(
        "llm_contracts: %s failed validation after %d attempts — dead-lettered (id=%s)",
        schema_name,
        attempts,
        entry.id,
    )
    return False, None
