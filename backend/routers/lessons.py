"""Adaptive lesson delivery: skill path, exercise reading, answer grading.

Learning Runtime half of a two-phase architecture (see backend/language_
library/ for Phase 1, run ahead of time by scripts/build_languages.py):
the fixed unit curriculum (get_lesson_exercises) is read-only here, never
generated on the spot. Free-form practice (get_practice_exercises) and
spaced-repetition review (get_review_session) stay AI-driven on purpose —
both are inherently personalized to one learner in the moment (their own
due words, their own live modality choice), not shared course content a
build pipeline could produce ahead of time for every learner."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, db, srs
from ..curriculum import ALPHABET_TOPIC, LessonRequest, all_units, get_unit, topic_es, units_for_level
from ..hf_client import hf_client
from ..language_library.storage import get_default_store, language_pair_key
from ..models import CEFRLevel, Exercise, ExerciseType
from .users import get_user_by_id_or_404

logger = logging.getLogger("lingua.lessons")

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
def get_lesson_exercises(user_id: str, unit_id: str, session: dict = Depends(auth.require_owner)) -> list[Exercise]:
    """The fixed unit curriculum — library-only, read from backend/
    language_library/ (built ahead of time by scripts/build_languages.py).
    404s if this (target_lang, native_lang, unit) hasn't been built yet —
    there is no on-demand AI fallback here; run the build script for
    whichever language pairs need to be available before students reach
    them.

    Free-form practice (get_practice_exercises below) and the review
    session (get_review_session) are NOT wired to the library on purpose
    — they personalize on the learner's own recent_mistakes/due items and
    let them pick modality live, which is exactly the kind of per-user
    adaptation a shared, pre-built library deliberately excludes (see
    language_library/__init__.py)."""
    user = get_user_by_id_or_404(user_id)
    unit = get_unit(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")

    pair_key = language_pair_key(user.target_lang, user.native_lang)
    persisted = get_default_store().load_course_asset(pair_key, unit.level.value, unit.id, "content")
    if persisted is None:
        raise HTTPException(status_code=404, detail="Esta unidad aún no está disponible en este idioma")
    return [Exercise(**item) for item in persisted]


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
    # How long the learner took to answer, in milliseconds — 0 means "not
    # measured" (the default for exercise types where timing doesn't
    # cleanly separate thinking time from network/AI latency, e.g.
    # speak_repeat's recording+transcription round trip). See srs.py's
    # grade_to_quality: a slow-but-correct answer schedules sooner review
    # than a quick one, instead of treating every correct answer the same.
    response_ms: int = 0
    # Content snapshot of the exercise being graded — persisted into
    # vocab_progress on first grading so a later /review session has enough
    # to work with (see srs.schedule_review). Optional: the frontend doesn't
    # always have a clean native_text (e.g. free_conversation_prompt).
    target_text: str = ""
    native_text: str = ""
    unit_id: str = ""


class AnswerResult(BaseModel):
    srs: dict = Field(default_factory=dict)


@router.post("/{user_id}/answer", response_model=AnswerResult)
def submit_answer(user_id: str, payload: AnswerRequest, session: dict = Depends(auth.require_owner)) -> AnswerResult:
    get_user_by_id_or_404(user_id)
    schedule = {}
    if payload.vocab_key:
        quality = srs.grade_to_quality(
            payload.correct, payload.attempts_before_correct, payload.response_ms or None
        )
        schedule = srs.schedule_review(
            user_id, payload.vocab_key, quality, payload.target_text, payload.native_text, payload.unit_id
        )
    return AnswerResult(srs=schedule)


@router.get("/{user_id}/review", response_model=PracticeResponse)
async def get_review_session(user_id: str, session: dict = Depends(auth.require_owner)) -> PracticeResponse:
    """A real spaced-repetition review session: pulls whatever vocab_progress
    rows are actually due right now (SM-2, per srs.due_review_items) and
    generates fresh exercises that specifically re-test those exact words —
    unlike the soft `recent_mistakes` hints woven into a normal lesson
    prompt, this is a deterministic, guaranteed-to-land review, closing the
    loop between "the learner got X wrong" and "X gets asked again on
    schedule." Returns an empty exercise list (not a 404) when nothing is
    due, so the frontend can show a calm "nothing to review yet" state."""
    user = get_user_by_id_or_404(user_id)
    items = srs.due_review_items(user_id, limit=10, exclude_prefix="academic:")
    exercises = await hf_client.generate_review_exercises(items, user.native_lang, user.target_lang)
    return PracticeResponse(unit_id=f"{PRACTICE_UNIT_PREFIX}-review", exercises=exercises)


class CompleteLessonRequest(BaseModel):
    unit_id: str
    score: float  # 0.0 - 1.0
    elapsed_seconds: int = 0


@router.post("/{user_id}/complete")
def complete_lesson(
    user_id: str, payload: CompleteLessonRequest, session: dict = Depends(auth.require_owner)
) -> dict:
    get_user_by_id_or_404(user_id)
    return srs.record_lesson_result(
        user_id, payload.unit_id, max(0.0, min(1.0, payload.score)), max(0, payload.elapsed_seconds)
    )
