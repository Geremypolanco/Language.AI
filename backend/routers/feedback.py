"""AI content feedback: thumbs up/down + an optional free-text report,
attachable to any piece of AI-generated content (a course module, a book, a
tutor reply, ...) by (content_type, content_id). This is the frontend-facing
half of the "guardrails against hallucinations" requirement — the model
output itself can't be perfectly validated, so the learner gets a direct
way to flag anything that reads wrong."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db

# Gated behind "signed in" (any account) — same reasoning as content.py:
# no per-resource ownership to check, just "a real logged-in user said this".
router = APIRouter(prefix="/api/feedback", tags=["feedback"])

_VALID_RATINGS = {"up", "down", "report"}
_MAX_NOTE_LENGTH = 1000


class FeedbackRequest(BaseModel):
    content_type: str = Field(max_length=64)
    content_id: str = Field(max_length=256)
    rating: str
    note: str = Field(default="", max_length=_MAX_NOTE_LENGTH)


@router.post("")
def submit_feedback(payload: FeedbackRequest, session: dict = Depends(auth.require_session)) -> dict:
    if payload.rating not in _VALID_RATINGS:
        raise HTTPException(status_code=422, detail="rating debe ser 'up', 'down' o 'report'")

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO ai_feedback (user_id, content_type, content_id, rating, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session["user_id"],
                payload.content_type,
                payload.content_id,
                payload.rating,
                payload.note.strip(),
                datetime.now(UTC).isoformat(),
            ),
        )
    return {"status": "recorded"}
