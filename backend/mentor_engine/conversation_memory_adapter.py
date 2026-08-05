"""Conversational Memory Adapter: a thin, read-only accessor over the
memory routers/conversation.py already builds and refreshes
(user_memories, updated every few turns by that router's _refresh_memory)
— deliberately not a second memory store. The rest of the mentor engine
needs to read this same memory (e.g. to show "última conversación" on the
Mentor Dashboard, or decide whether "continue from yesterday" phrasing
even makes sense) without importing router code or duplicating the
summarization logic that already exists there.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .. import db


def get_memory(user_id: str) -> str:
    with db.cursor() as cur:
        cur.execute("SELECT content FROM user_memories WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row["content"] if row else ""


def has_recent_conversation(user_id: str, within_hours: int = 24) -> bool:
    """Whether user_memories was updated recently enough that "sigamos
    donde lo dejamos" is actually meaningful — a memory summary from
    three weeks ago is stale context, not continuity."""
    with db.cursor() as cur:
        cur.execute("SELECT updated_at FROM user_memories WHERE user_id=?", (user_id,))
        row = cur.fetchone()
    if not row:
        return False
    updated_at = datetime.fromisoformat(row["updated_at"])
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - updated_at) <= timedelta(hours=within_hours)
