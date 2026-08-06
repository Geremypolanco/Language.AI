"""Per-job_type registration of executors and validators — the seam that
makes this infrastructure "reutilizable para cualquier tipo de asset
futuro" rather than audio-specific. Adding a new asset type (images,
embeddings, ...) later means writing one executors/<type>.py module and
one register() call in bootstrap.py — nothing here, in manager.py, or in
worker.py changes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

Executor = Callable[[dict[str, Any]], Awaitable[Any]]
# Returns a list of problem descriptions; empty list means the result is valid.
Validator = Callable[[Any], list[str]]

_executors: dict[str, Executor] = {}
_validators: dict[str, Validator] = {}


def register(job_type: str, executor: Executor, validator: Validator) -> None:
    _executors[job_type] = executor
    _validators[job_type] = validator


def get_executor(job_type: str) -> Executor | None:
    return _executors.get(job_type)


def get_validator(job_type: str) -> Validator | None:
    return _validators.get(job_type)


def registered_job_types() -> list[str]:
    return list(_executors.keys())
