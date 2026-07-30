"""Adaptive placement test, run during onboarding before a profile exists yet.

Mirrors the mechanic real placement tests use (Duolingo's included): start at
a medium level, get harder after a correct answer, easier after a miss, and
converge on a recommended starting level after a handful of questions —
rather than asking the learner to just guess their own CEFR level from a
dropdown. Stateless like the rest of this app's auth: the client resubmits
its answer history each call instead of the server tracking a session.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth
from ..curriculum import LessonRequest, units_for_level
from ..hf_client import hf_client
from ..models import CEFRLevel, Exercise

router = APIRouter(prefix="/api/placement", tags=["placement"])

_LEVELS = [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2]
_START_INDEX = 1  # A2 — Duolingo's placement test also opens at medium difficulty
_MAX_QUESTIONS = 6


class PlacementAnswer(BaseModel):
    level: CEFRLevel
    correct: bool


class PlacementRequest(BaseModel):
    native_lang: str
    target_lang: str
    interests: list[str] = Field(default_factory=list)
    history: list[PlacementAnswer] = Field(default_factory=list)


class PlacementResponse(BaseModel):
    done: bool
    question_number: int = 0
    total_questions: int = _MAX_QUESTIONS
    level: CEFRLevel | None = None
    exercise: Exercise | None = None
    recommended_level: CEFRLevel | None = None


def _level_index(history: list[PlacementAnswer]) -> int:
    idx = _START_INDEX
    for ans in history:
        idx = min(idx + 1, len(_LEVELS) - 1) if ans.correct else max(idx - 1, 0)
    return idx


@router.post("", response_model=PlacementResponse)
async def next_placement_question(payload: PlacementRequest, request: Request) -> PlacementResponse:
    if not auth.verify_pending(request.cookies.get(auth.PENDING_COOKIE)):
        raise HTTPException(status_code=401, detail="Sign in with Google first")

    idx = _level_index(payload.history)
    if len(payload.history) >= _MAX_QUESTIONS:
        return PlacementResponse(done=True, recommended_level=_LEVELS[idx])

    level = _LEVELS[idx]
    unit = units_for_level(level)[0]
    req = LessonRequest(
        unit=unit,
        native_lang=payload.native_lang,
        target_lang=payload.target_lang,
        interests=payload.interests,
        recent_mistakes=[],
    )
    exercises = await hf_client.generate_exercises(req)
    exercise = exercises[0] if exercises else None
    return PlacementResponse(
        done=False,
        question_number=len(payload.history) + 1,
        level=level,
        exercise=exercise,
    )
