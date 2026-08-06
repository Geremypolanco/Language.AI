"""The single place that wires job_type -> (executor, validator). Called
once at process startup (see backend/main.py's lifespan and
scripts/run_worker.py) before the worker loop starts claiming jobs.

Adding a new asset type later: write executors/<type>.py (an
`execute(payload) -> result` coroutine + a `validate(result) ->
list[str]`), import it here, and add one register() call — nothing
elsewhere (manager.py, worker.py, scanner.py's generic shape) changes."""

from __future__ import annotations

from . import registry
from .executors import audio as audio_executor


def register_all() -> None:
    registry.register("audio_unit", audio_executor.execute, audio_executor.validate)
