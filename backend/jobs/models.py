"""The Job record itself — see manager.py for the operations on it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Job:
    id: int
    job_type: str
    dedupe_key: str
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    last_error: str
    created_at: str
    updated_at: str
    run_after: str
