"""Adaptive lesson delivery: skill path, exercise generation, answer grading."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db, srs
from ..curriculum import ALPHABET_TOPIC, LessonRequest, all_units, get_unit, topic_es, units_for_level
from ..hf_client import hf_client
from ..models import CEFRLevel, Exercise, ExerciseType
from .users import get_user_by_id_or_404

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


class UnitNode(BaseModel):
    id: str
    topic: str
    # Spanish label for `topic` — the skill-tree topic keys are internal,
    # language-agnostic English strings (see curriculum.py's _TOPICS_BY_LEVEL);
    # the UI should never show those raw keys to a Spanish-speaking learner.
    topic_es: str
    level: CEFRLevel
    order: int
    state: str  # "available" | "mastered" — nothing is ever locked; the
    # learner decides what to practice first, the level/order is only a
    # suggested default ordering, not a gate.
    best_score: float = 0.0


@router.get("/{user_id}/path", response_model=list[UnitNode])
def get_path(user_id: str, session: dict = Depends(auth.require_owner)) -> list[UnitNode]:
    get_user_by_id_or_404(user_id)
    with db.cursor() as cur:
        cur.execute("SELECT unit_id, best_score, mastered FROM unit_mastery WHERE user_id=?", (user_id,))
        mastery = {r["unit_id"]: r for r in cur.fetchall()}

    nodes: list[UnitNode] = []
    for unit in all_units():
        m = mastery.get(unit.id)
        best = m["best_score"] if m else 0.0
        state = "mastered" if m and m["mastered"] else "available"
        nodes.append(
            UnitNode(
                id=unit.id,
                topic=unit.topic,
                topic_es=topic_es(unit.topic),
                level=unit.level,
                order=unit.order,
                state=state,
                best_score=best,
            )
        )
    return nodes


@router.get("/{user_id}/unit/{unit_id}", response_model=list[Exercise])
async def get_lesson_exercises(
    user_id: str, unit_id: str, session: dict = Depends(auth.require_owner)
) -> list[Exercise]:
    user = get_user_by_id_or_404(user_id)
    unit = get_unit(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")

    req = LessonRequest(
        unit=unit,
        native_lang=user.native_lang,
        target_lang=user.target_lang,
        interests=user.interests,
        recent_mistakes=srs.recent_mistakes(user_id),
    )
    return await hf_client.generate_exercises(req)


PRACTICE_UNIT_PREFIX = "practice"


class PracticeRequest(BaseModel):
    exercise_type: ExerciseType
    level: CEFRLevel | None = None


class PracticeResponse(BaseModel):
    unit_id: str
    exercises: list[Exercise]


@router.post("/{user_id}/practice", response_model=PracticeResponse)
async def get_practice_exercises(
    user_id: str, payload: PracticeRequest, session: dict = Depends(auth.require_owner)
) -> PracticeResponse:
    """Free-form skill practice: the learner picks the modality (reading/
    writing, listening, speaking, images, conversation) instead of following
    a unit's fixed exercise mix. Uses a stable synthetic unit id so /complete
    can still award XP/gems/streak through the normal path."""
    user = get_user_by_id_or_404(user_id)
    level = payload.level or user.level
    units = units_for_level(level)
    if not units:
        raise HTTPException(status_code=404, detail="No hay unidades para ese nivel")
    # Skip the Alphabet unit as this level's content seed: free practice lets
    # the learner pick an arbitrary modality (conversation, translation,
    # listening, ...), and the alphabet unit only exists to teach individual
    # letters/sounds — a mismatch that used to leak "teach one letter at a
    # time" instructions into e.g. a free-conversation practice request (see
    # build_exercise_generation_prompt's alphabet_unit_note gating).
    unit = next((u for u in units if u.topic != ALPHABET_TOPIC), units[0])

    req = LessonRequest(
        unit=unit,
        native_lang=user.native_lang,
        target_lang=user.target_lang,
        interests=user.interests,
        recent_mistakes=srs.recent_mistakes(user_id),
    )
    exercises = await hf_client.generate_exercises(req, mix_override=[payload.exercise_type] * 5)
    synthetic_unit_id = f"{PRACTICE_UNIT_PREFIX}-{payload.exercise_type.value}-{level.value}"
    return PracticeResponse(unit_id=synthetic_unit_id, exercises=exercises)


class AnswerRequest(BaseModel):
    vocab_key: str = ""
    correct: bool
    attempts_before_correct: int = 0


class AnswerResult(BaseModel):
    srs: dict = Field(default_factory=dict)


@router.post("/{user_id}/answer", response_model=AnswerResult)
def submit_answer(user_id: str, payload: AnswerRequest, session: dict = Depends(auth.require_owner)) -> AnswerResult:
    get_user_by_id_or_404(user_id)
    schedule = {}
    if payload.vocab_key:
        quality = srs.grade_to_quality(payload.correct, payload.attempts_before_correct)
        schedule = srs.schedule_review(user_id, payload.vocab_key, quality)
    return AnswerResult(srs=schedule)


class CompleteLessonRequest(BaseModel):
    unit_id: str
    score: float  # 0.0 - 1.0
    elapsed_seconds: int = 0


@router.post("/{user_id}/complete")
def complete_lesson(user_id: str, payload: CompleteLessonRequest, session: dict = Depends(auth.require_owner)) -> dict:
    get_user_by_id_or_404(user_id)
    return srs.record_lesson_result(
        user_id, payload.unit_id, max(0.0, min(1.0, payload.score)), max(0, payload.elapsed_seconds)
    )
