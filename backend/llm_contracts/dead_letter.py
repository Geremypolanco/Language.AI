"""Dead-letter queue for LLM outputs that never validated.

A generation that fails schema validation after all retries lands here —
visible for human triage — it never silently enters a lesson, a grade, or
a recommendation. Nothing in this queue ever reaches the learner.

Persistence: JSONL file (one entry per line), gitignored, never committed.
Override the directory with the LINGUA_DEAD_LETTER_DIR env var.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


def _default_dir() -> str:
    return os.environ.get("LINGUA_DEAD_LETTER_DIR") or os.path.join(
        os.getcwd(), "data", "dead_letters"
    )


@dataclass
class DeadLetterEntry:
    """One quarantined LLM output."""

    id: str
    at: str  # ISO-8601 UTC timestamp
    schema: str  # human-readable contract name, e.g. "ExerciseList"
    errors: list[str]  # validation failure messages from the last attempt
    attempts: int  # how many attempts were made before giving up
    context: dict = field(default_factory=dict)  # unit id, user id, … — never secrets

    @classmethod
    def new(
        cls,
        schema: str,
        errors: list[str],
        attempts: int,
        context: dict | None = None,
    ) -> "DeadLetterEntry":
        return cls(
            id=uuid.uuid4().hex,
            at=datetime.now(UTC).isoformat(),
            schema=schema,
            errors=list(errors),
            attempts=attempts,
            context=dict(context or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeadLetterEntry":
        return cls(
            id=str(data.get("id", "")),
            at=str(data.get("at", "")),
            schema=str(data.get("schema", "")),
            errors=list(data.get("errors", [])),
            attempts=int(data.get("attempts", 0)),
            context=dict(data.get("context", {}) or {}),
        )


class DeadLetterQueue:
    """File-backed dead-letter queue. `push` appends to the in-memory list
    and to the JSONL triage file; `list` reads newest-first for triage."""

    def __init__(self, directory: str | None = None) -> None:
        self._dir = directory or _default_dir()
        self._path = os.path.join(self._dir, "dead_letters.jsonl")
        self._entries: list[DeadLetterEntry] = []
        self._load_existing()

    @property
    def path(self) -> str:
        return self._path

    def _load_existing(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(DeadLetterEntry.from_dict(json.loads(line)))
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # A corrupt triage file must never break the app; the in-memory
            # queue still works and new pushes rewrite… nothing — we keep
            # appending. Triage visibility degrades, the app doesn't.
            pass

    def push(self, entry: DeadLetterEntry) -> DeadLetterEntry:
        self._entries.append(entry)
        try:
            os.makedirs(self._dir, exist_ok=True)
            # Atomic-ish append: write to temp then append bytes. A plain
            # append is fine for this app's single-process model; the
            # temp-file dance only guards against a half-written line on
            # crash mid-write.
            fd, tmp = tempfile.mkstemp(dir=self._dir, prefix=".dlq-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
                with open(tmp, "rb") as src, open(self._path, "ab") as dst:
                    dst.write(src.read())
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        except OSError:
            pass  # persistence is best-effort; the in-memory entry remains
        return entry

    def list(self, limit: int = 200) -> list[DeadLetterEntry]:
        """Newest first — triage looks at the most recent failures."""
        return list(reversed(self._entries[-limit:]))

    def clear(self) -> None:
        self._entries.clear()
        try:
            if os.path.exists(self._path):
                os.unlink(self._path)
        except OSError:
            pass

    def __len__(self) -> int:
        return len(self._entries)


# Process-wide singleton used by validate_or_retry when no explicit queue
# is passed. Tests inject their own queue pointed at a tmp dir.
dead_letters = DeadLetterQueue()
