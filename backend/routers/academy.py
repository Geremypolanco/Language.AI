"""University-prep academy: self-paced, accelerated study tracks across ~60
academic fields. This is explicitly NOT an accredited program; every
response that reaches the UI is meant to be shown next to a persistent
disclaimer (enforced in the frontend, not here).

This router is the Learning Runtime half of a two-phase architecture:
- Phase 1, Content Production (backend/academy_library/, run ahead of
  time by scripts/build_academy.py): the ONLY place curriculum, course
  content, assignments, and practice scenarios are generated. All AI
  calls for this content live there, never here.
- Phase 2, Learning Runtime (this file): reads whatever Phase 1 already
  published. A (field, level) the pipeline hasn't built yet is served
  as a 404 ("aún no disponible"), never generated on the spot — there is
  no on-demand fallback to an AI model anywhere in this router for
  curriculum/course/assignment/scenario content. Grading (quiz/exam/
  assignment/scenario-response evaluation) is the one AI dependency this
  runtime keeps: evaluating what a student already wrote is reading +
  judging their input, not producing new academic content, and every
  quiz/exam question's rubric_note needed to grade it was itself
  produced in Phase 1.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import academy, auth, db
from ..academy_library.storage import get_default_store
from ..hf_client import hf_client
from ..learning_engine import (
    achievements,
    analytics,
    competency,
    concept_review,
    goals,
    grading,
    knowledge_graph,
    learning_style,
    motivation,
    portfolio,
    predictions,
    recommendations,
    student_profile,
)
from ..mentor_engine import daily_planner as mentor_daily_planner
from ..mentor_engine import goal_planner
from ..mentor_engine import insights as mentor_insights
from ..mentor_engine import knowledge_profile as mentor_knowledge_profile
from ..mentor_engine import mentor_engine as ai_mentor
from ..models import (
    AcademicField,
    AcademicLevel,
    AcademyEnrollment,
    AcademyProgress,
    Assignment,
    Curriculum,
    CourseContent,
    CourseStub,
)
from .users import get_user_by_id_or_404

logger = logging.getLogger("lingua.academy")

router = APIRouter(prefix="/api/academy", tags=["academy"])


@router.get("/fields", response_model=list[AcademicField])
def get_fields() -> list[AcademicField]:
    return academy.all_fields()


def _course_id(field_id: str, level: AcademicLevel, order: int) -> str:
    return f"{field_id}:{level.value}:{order}"


def _stubs_from_courses(field_id: str, level: AcademicLevel, courses: list[dict], order_offset: int = 0) -> list[CourseStub]:
    return [
        CourseStub(id=_course_id(field_id, level, i), order=order_offset + i, title=c["title"], description=c["description"])
        for i, c in enumerate(courses)
    ]


def _load_curriculum(field: AcademicField, level: AcademicLevel, content_lang: str) -> Curriculum | None:
    """Library-only: returns None if scripts/build_academy.py hasn't built
    this (field, level) yet. Never calls an AI model — content_lang is
    accepted only so callers don't need special-casing, since the
    persisted curriculum's language was fixed at build time."""
    store = get_default_store()
    persisted = store.load_curriculum(field.id, level.value)
    if persisted is None:
        return None
    courses = _stubs_from_courses(field.id, level, persisted["courses"])
    # A specialization's served curriculum prepends its base field's
    # already-built courses ahead of its own — see academy_library/
    # build.py's module docstring for why the specialization's own
    # build never regenerates (or stores a second copy of) them.
    if field.base_field_id:
        base_field = academy.get_field(field.base_field_id)
        base_persisted = store.load_curriculum(field.base_field_id, level.value) if base_field else None
        if base_field and base_persisted:
            base_stubs = _stubs_from_courses(base_field.id, level, base_persisted["courses"])
            courses = base_stubs + courses
            for i, stub in enumerate(courses):
                stub.order = i
    return Curriculum(field_id=field.id, field_name=field.name, level=level, level_label=level.label_es, courses=courses)


def _build_enrollment(
    field: AcademicField, level: AcademicLevel, enrolled_at: str, content_lang: str
) -> AcademyEnrollment:
    return AcademyEnrollment(
        field_id=field.id, field_name=field.name, tutor_name=field.tutor_name, icon=field.icon,
        category=field.category, level=level, level_label=level.label_es, enrolled_at=enrolled_at,
        content_lang=content_lang,
    )


def _get_enrollment_row(user_id: str) -> Any:
    with db.cursor() as cur:
        cur.execute(
            "SELECT field_id, level, enrolled_at, content_lang FROM academy_enrollment WHERE user_id=?", (user_id,)
        )
        return cur.fetchone()


class EnrollRequest(BaseModel):
    field_id: str
    level: AcademicLevel
    # Optional — the language to study this career's content in. Defaults to
    # the learner's native_lang (the previous, only behavior) when omitted,
    # but a learner can pick a different one, e.g. to study in their target
    # language for extra immersion.
    content_lang: str | None = None


@router.post("/{user_id}/enroll", response_model=AcademyEnrollment)
def enroll(user_id: str, payload: EnrollRequest, session: dict = Depends(auth.require_owner)) -> AcademyEnrollment:
    user = get_user_by_id_or_404(user_id)
    field = academy.get_field(payload.field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")

    content_lang = payload.content_lang or user.native_lang
    enrolled_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at, content_lang) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET field_id=excluded.field_id, level=excluded.level, "
            "enrolled_at=excluded.enrolled_at, content_lang=excluded.content_lang",
            (user_id, field.id, payload.level.value, enrolled_at, content_lang),
        )
    return _build_enrollment(field, payload.level, enrolled_at, content_lang)


@router.get("/{user_id}/progress", response_model=AcademyProgress)
async def get_progress(user_id: str, session: dict = Depends(auth.require_owner)) -> AcademyProgress:
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        return AcademyProgress(enrollment=None)

    field = academy.get_field(row["field_id"])
    level = AcademicLevel(row["level"])
    if not field:
        return AcademyProgress(enrollment=None)

    # content_lang is '' for enrollments made before this column existed —
    # fall back to native_lang, the only behavior back then.
    content_lang = row["content_lang"] or user.native_lang
    enrollment = _build_enrollment(field, level, row["enrolled_at"], content_lang)
    curriculum = _load_curriculum(field, level, content_lang)
    # Not built yet — level.course_count is the nominal size so the UI
    # still has something sane to show instead of a broken "0 of 0".
    total_courses = len(curriculum.courses) if curriculum else level.course_count

    with db.cursor() as cur:
        cur.execute("SELECT course_id FROM academy_course_progress WHERE user_id=?", (user_id,))
        completed = [r["course_id"] for r in cur.fetchall()]

    return AcademyProgress(enrollment=enrollment, completed_course_ids=completed, total_courses=total_courses)


@router.get("/{user_id}/curriculum", response_model=Curriculum)
async def get_curriculum(user_id: str, session: dict = Depends(auth.require_owner)) -> Curriculum:
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])
    curriculum = _load_curriculum(field, level, row["content_lang"] or user.native_lang)
    if curriculum is None:
        raise HTTPException(status_code=404, detail="El currículo de esta carrera aún no está disponible — está pendiente de construir")
    return curriculum


async def _resolve_course(user_id: str, course_id: str):
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])
    content_lang = row["content_lang"] or user.native_lang

    curriculum = _load_curriculum(field, level, content_lang)
    if curriculum is None:
        raise HTTPException(status_code=404, detail="El currículo de esta carrera aún no está disponible — está pendiente de construir")
    stub = next((c for c in curriculum.courses if c.id == course_id), None)
    if not stub:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    # A specialization's curriculum can contain course ids owned by its base
    # field (see _load_curriculum) — course_id's own field_id prefix is
    # always the TRUE owner of that course's content, so library lookups
    # below must use that field, not necessarily the enrolled one.
    owning_field = academy.get_field(course_id.split(":")[0]) or field
    return user, owning_field, level, stub, content_lang


@router.get("/{user_id}/courses/{course_id}", response_model=CourseContent)
async def get_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseContent:
    """Library-only — see this module's docstring. 404s until the
    Content Production Pipeline has actually built this course."""
    _user, field, level, stub, _content_lang = await _resolve_course(user_id, course_id)
    persisted = get_default_store().load_course_asset(field.id, level.value, course_id, "content")
    if persisted is None:
        raise HTTPException(status_code=404, detail="El contenido de este curso aún no está disponible")
    return CourseContent(id=stub.id, title=stub.title, modules=persisted["modules"])


@router.get("/{user_id}/courses/{course_id}/glossary")
async def get_glossary(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Key terms + plain-language definitions for this course. Library-only
    — 404s until the course has actually been built (see backend/
    academy_library)."""
    _user, field, level, _stub, _content_lang = await _resolve_course(user_id, course_id)
    data = get_default_store().load_course_asset(field.id, level.value, course_id, "glossary")
    if data is None:
        raise HTTPException(status_code=404, detail="El glosario de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/quiz")
async def get_quiz(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Library-only, like get_glossary above."""
    _user, field, level, _stub, _content_lang = await _resolve_course(user_id, course_id)
    data = get_default_store().load_course_asset(field.id, level.value, course_id, "quiz")
    if data is None:
        raise HTTPException(status_code=404, detail="El quiz de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/exam")
async def get_exam(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Library-only, like get_glossary above."""
    _user, field, level, _stub, _content_lang = await _resolve_course(user_id, course_id)
    data = get_default_store().load_course_asset(field.id, level.value, course_id, "exam")
    if data is None:
        raise HTTPException(status_code=404, detail="El examen de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/scenario")
async def get_practice_scenario(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """A realistic, hands-on case/scenario for this course — the practical
    complement to the theory in get_course, for fields (nursing, engineering,
    business, ...) where reading alone isn't enough. Library-only, like
    get_glossary — 404s until the course has actually been built."""
    _user, field, level, _stub, _content_lang = await _resolve_course(user_id, course_id)
    scenario = get_default_store().load_course_asset(field.id, level.value, course_id, "scenario")
    if scenario is None:
        raise HTTPException(status_code=404, detail="El caso práctico de este curso aún no está disponible")
    return {"scenario": scenario}


class ScenarioResponseRequest(BaseModel):
    scenario: str
    response: str


@router.post("/{user_id}/courses/{course_id}/scenario/feedback")
async def get_scenario_feedback(
    user_id: str, course_id: str, payload: ScenarioResponseRequest, session: dict = Depends(auth.require_owner)
) -> dict:
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    content_lang = (row["content_lang"] if row else "") or user.native_lang
    feedback = await hf_client.grade_practice_response(payload.scenario, payload.response, content_lang)
    # Persisted so it can appear in the student's portfolio (see
    # learning_engine/portfolio.py) — previously this feedback was shown
    # once and then lost, even though it's real evidence of applied work.
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_scenario_submission (user_id, course_id, scenario, response, feedback, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, course_id, payload.scenario, payload.response, feedback, datetime.now(UTC).isoformat()),
        )
    return {"feedback": feedback}


def _get_submission_rows(user_id: str, course_id: str) -> dict[str, Any]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT assignment_id, response, feedback, grade FROM academy_assignment_submission "
            "WHERE user_id=? AND course_id=?",
            (user_id, course_id),
        )
        return {r["assignment_id"]: r for r in cur.fetchall()}


@router.get("/{user_id}/courses/{course_id}/assignments", response_model=list[Assignment])
async def get_assignments(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> list[Assignment]:
    """Real, gradeable schoolwork for this course — a tarea, an informe, and
    a proyecto — on top of the theory in get_course and the ungraded
    practice scenario. Submission status/feedback/grade persist per user.
    Library-only — 404s until the course has actually been built."""
    _user, field, level, _stub, _content_lang = await _resolve_course(user_id, course_id)
    raw = get_default_store().load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
        raise HTTPException(status_code=404, detail="Las tareas de este curso aún no están disponibles")
    submissions = _get_submission_rows(user_id, course_id)
    assignments = []
    for item in raw:
        sub = submissions.get(item["id"])
        assignments.append(
            Assignment(
                id=item["id"],
                type=item["type"],
                title=item["title"],
                instructions=item["instructions"],
                submitted=sub is not None,
                response=sub["response"] if sub else "",
                feedback=sub["feedback"] if sub else "",
                grade=sub["grade"] if sub else "",
            )
        )
    return assignments


class AssignmentSubmitRequest(BaseModel):
    response: str


@router.post("/{user_id}/courses/{course_id}/assignments/{assignment_id}/submit")
async def submit_assignment(
    user_id: str,
    course_id: str,
    assignment_id: str,
    payload: AssignmentSubmitRequest,
    session: dict = Depends(auth.require_owner),
) -> dict:
    _user, field, level, _stub, content_lang = await _resolve_course(user_id, course_id)
    raw = get_default_store().load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
        raise HTTPException(status_code=404, detail="Las tareas de este curso aún no están disponibles")
    assignment = next((a for a in raw if a["id"] == assignment_id), None)
    if not assignment:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    result = await hf_client.grade_assignment_submission(
        assignment["title"], assignment["instructions"], payload.response, content_lang
    )
    submitted_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_assignment_submission "
            "(user_id, course_id, assignment_id, response, feedback, grade, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (user_id, assignment_id) DO UPDATE SET response=excluded.response, "
            "feedback=excluded.feedback, grade=excluded.grade, submitted_at=excluded.submitted_at",
            (user_id, course_id, assignment_id, payload.response, result["feedback"], result["grade"], submitted_at),
        )
    return {"grade": result["grade"], "feedback": result["feedback"]}


class CompleteCourseRequest(BaseModel):
    elapsed_seconds: int = 0


@router.post("/{user_id}/courses/{course_id}/complete", response_model=AcademyProgress)
async def complete_course(
    user_id: str, course_id: str, payload: CompleteCourseRequest = CompleteCourseRequest(),
    session: dict = Depends(auth.require_owner),
) -> AcademyProgress:
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")

    completed_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, course_id) DO UPDATE SET elapsed_seconds=academy_course_progress.elapsed_seconds + excluded.elapsed_seconds",
            (user_id, course_id, completed_at, max(0, payload.elapsed_seconds)),
        )
    return await get_progress(user_id, session)


# ── Learning engine: competencies, quiz/exam grading, recommendations,
# achievements, concept review (backend/learning_engine/) ──────────────────


class QuizSubmitRequest(BaseModel):
    # Question index (as a string, matching how JSON object keys arrive) ->
    # the student's given answer.
    answers: dict[str, str]


async def _submit_quiz_or_exam(user_id: str, course_id: str, kind: str, payload: "QuizSubmitRequest") -> dict:
    _user, field, level, _stub, content_lang = await _resolve_course(user_id, course_id)
    data = get_default_store().load_course_asset(field.id, level.value, course_id, kind)
    if data is None:
        raise HTTPException(status_code=404, detail="Esta evaluación aún no está disponible")

    result = await grading.grade_submission(data["questions"], payload.answers, content_lang)
    submitted_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_quiz_submission (user_id, course_id, kind, score, submitted_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, course_id, kind, result["score"], submitted_at),
        )
        # Per-question detail — academy_quiz_submission's aggregate score
        # alone can't answer "which questions do students actually fail?"
        # (see learning_engine/analytics.py's admin-facing summary).
        for i, (question, res) in enumerate(zip(data["questions"], result["results"])):
            cur.execute(
                "INSERT INTO academy_question_attempt "
                "(user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, course_id, kind, i, question.get("question", ""), int(res["correct"]), submitted_at),
            )
    new_competency = competency.record_result(user_id, field.id, course_id, result["score"])
    return {"score": result["score"], "results": result["results"], "competency_score": new_competency}


@router.post("/{user_id}/courses/{course_id}/quiz/submit")
async def submit_quiz(user_id: str, course_id: str, payload: QuizSubmitRequest, session: dict = Depends(auth.require_owner)) -> dict:
    return await _submit_quiz_or_exam(user_id, course_id, "quiz", payload)


@router.post("/{user_id}/courses/{course_id}/exam/submit")
async def submit_exam(user_id: str, course_id: str, payload: QuizSubmitRequest, session: dict = Depends(auth.require_owner)) -> dict:
    return await _submit_quiz_or_exam(user_id, course_id, "exam", payload)


def _course_titles_for(field_id: str, level: AcademicLevel) -> dict[str, str]:
    persisted = get_default_store().load_curriculum(field_id, level.value)
    if not persisted:
        return {}
    return {
        _course_id(field_id, level, i): c["title"]
        for i, c in enumerate(persisted["courses"])
    }


def _resolve_titles_for_course_ids(course_ids: list[str]) -> dict[str, str]:
    """Like _course_titles_for, but for an arbitrary set of course ids that
    may span several (field, level) pairs — e.g. a portfolio covering every
    field a student has ever studied, not just their current enrollment."""
    field_levels: set[tuple[str, str]] = set()
    for cid in course_ids:
        parts = cid.split(":")
        if len(parts) == 3:
            field_levels.add((parts[0], parts[1]))

    titles: dict[str, str] = {}
    for field_id, level_str in field_levels:
        try:
            level = AcademicLevel(level_str)
        except ValueError:
            continue
        titles.update(_course_titles_for(field_id, level))
    return titles


def _mentor_context_for(user_id: str) -> tuple[str | None, list[str], dict[str, str]]:
    """(field_id, course_ids_in_order, titles) for whatever the student is
    currently enrolled in — or (None, [], {}) with no enrollment, which
    every mentor_engine entry point treats as "give a real, narrower
    answer", never a 404 (same precedent as get_unified_competencies and
    get_student_profile above). Uses the same sync, persisted-library-only
    _course_titles_for as /recommendation and /competencies — an
    unbuilt curriculum means an empty course list here too, not a live
    AI call from inside the mentor engine."""
    row = _get_enrollment_row(user_id)
    if not row:
        return None, [], {}
    field = academy.get_field(row["field_id"])
    if not field:
        return None, [], {}
    level = AcademicLevel(row["level"])
    titles = _course_titles_for(field.id, level)
    return field.id, list(titles.keys()), titles


@router.get("/{user_id}/competencies")
def get_competencies(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Real per-course mastery scores (see learning_engine/competency.py) —
    replaces "percent of course complete" as the main progress signal.
    Empty until the student has submitted at least one quiz or exam."""
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])

    titles = _course_titles_for(field.id, level)
    scores = competency.get_competencies(user_id, field.id)
    weak = recommendations.courses_needing_review(user_id, field.id, list(titles.keys()))
    return {
        "competencies": [
            {**c, "title": titles.get(c["course_id"], c["course_id"])} for c in scores
        ],
        "strengths_and_weaknesses": competency.strengths_and_weaknesses(user_id, field.id),
        "courses_needing_review": [{"course_id": cid, "title": titles.get(cid, cid)} for cid in weak],
    }


@router.get("/{user_id}/competencies/unified")
def get_unified_competencies(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Academy + Language competencies side by side (learning_engine/
    competency.get_unified_competencies) — unlike /competencies above,
    this never 404s on "not enrolled": a student who's only doing
    languages (or only Academy) still gets a real, if partial, view."""
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    field_id = row["field_id"] if row else None
    return competency.get_unified_competencies(user_id, field_id)


@router.get("/{user_id}/predictions")
async def get_predictions(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Transparent, rule-based risk/pace signals — see learning_engine/
    predictions.py's module docstring for why these are heuristics, not a
    trained ML model. forgetting_risk and dropout_risk work for every
    student regardless of enrollment; time_to_mastery is only meaningful
    for an active Academy enrollment, so it's null without one."""
    user = get_user_by_id_or_404(user_id)
    result: dict[str, Any] = {
        "forgetting_risk": predictions.forgetting_risk(user_id),
        "dropout_risk": predictions.dropout_risk(user_id),
        "time_to_mastery": None,
    }

    row = _get_enrollment_row(user_id)
    if row:
        field = academy.get_field(row["field_id"])
        level = AcademicLevel(row["level"])
        if field:
            content_lang = row["content_lang"] or user.native_lang
            curriculum = _load_curriculum(field, level, content_lang)
            total_courses = len(curriculum.courses) if curriculum else level.course_count
            with db.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM academy_course_progress WHERE user_id=? AND course_id LIKE ?",
                    (user_id, f"{field.id}:{level.value}:%"),
                )
                completed_count = cur.fetchone()["c"]
            result["time_to_mastery"] = predictions.time_to_mastery_estimate(
                row["enrolled_at"], completed_count, total_courses
            )

    return result


@router.get("/{user_id}/learning-style")
def get_learning_style(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Conversational vs. written/structured practice ratio — inferred
    from real activity (learning_engine/learning_style.py), never asked
    at onboarding."""
    get_user_by_id_or_404(user_id)
    return learning_style.infer_learning_style(user_id)


@router.get("/{user_id}/motivation")
def get_motivation(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """A specific, non-generic motivation signal from the student's own
    recent lessons (learning_engine/motivation.py) — "frustracion",
    "buen_momentum", "estancado", or "neutral"/"sin_datos"."""
    get_user_by_id_or_404(user_id)
    return motivation.detect_signal(user_id)


@router.get("/{user_id}/mentor/dashboard")
def get_mentor_dashboard(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """The AI Mentor Engine's single combined view — see mentor_engine/
    mentor_engine.py's module docstring for exactly which existing
    Learning Intelligence Engine data every section reads from (nothing
    here is tracked twice). Works without an Academy enrollment, same as
    /profile and /competencies/unified above."""
    user = get_user_by_id_or_404(user_id)
    field_id, course_ids, titles = _mentor_context_for(user_id)
    return ai_mentor.get_mentor_dashboard(user_id, field_id, course_ids, titles, level=user.level)


@router.get("/{user_id}/mentor/daily-plan")
def get_daily_plan(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    """"Hoy deberías..." — a short, ordered, always-justified list of
    concrete actions (see mentor_engine/daily_planner.py). Never empty
    without a real reason: an empty list just means there's genuinely
    nothing pending right now, not a missing feature."""
    user = get_user_by_id_or_404(user_id)
    field_id, course_ids, titles = _mentor_context_for(user_id)
    return mentor_daily_planner.build_daily_plan(user_id, field_id, course_ids, titles, user.level)


@router.get("/{user_id}/mentor/insights")
def get_mentor_insights(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    """Post-session observations (mentor_engine/insights.py) — empty
    without an Academy enrollment, since these compare quiz-submission
    trends and mistake concentration that only exist there."""
    get_user_by_id_or_404(user_id)
    field_id, course_ids, titles = _mentor_context_for(user_id)
    if not field_id:
        return []
    return mentor_insights.generate_insights(user_id, field_id, course_ids, titles)


@router.get("/{user_id}/mentor/knowledge-profile")
def get_knowledge_profile(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    """Every concept in the student's field, with a real mastery status
    (Unknown/Learning/Practicing/Mastered/Expert) — see mentor_engine/
    knowledge_profile.py. Empty without an Academy enrollment."""
    get_user_by_id_or_404(user_id)
    field_id, _, _ = _mentor_context_for(user_id)
    if not field_id:
        return []
    return mentor_knowledge_profile.get_knowledge_profile(user_id, field_id)


@router.get("/{user_id}/recommendation")
def get_recommendation(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """The next course to study, given the student's current competency
    scores and curriculum order — see learning_engine/recommendations.py
    for exactly what this does and doesn't account for."""
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])

    titles = _course_titles_for(field.id, level)
    course_ids = list(titles.keys())
    next_course = recommendations.recommend_next_course(user_id, field.id, course_ids)
    specializations = recommendations.suggest_specializations(field.id)
    return {
        "next_course_id": next_course,
        "next_course_title": titles.get(next_course) if next_course else None,
        "all_courses_mastered": next_course is None and bool(course_ids),
        "difficulty_signal": recommendations.difficulty_signal(user_id, next_course) if next_course else None,
        "suggested_specializations": [
            {"id": f.id, "name": f.name, "description": f.description} for f in specializations
        ],
    }


@router.get("/{user_id}/achievements")
def get_achievements(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        return []
    field = academy.get_field(row["field_id"])
    if not field:
        return []
    level = AcademicLevel(row["level"])
    titles = _course_titles_for(field.id, level)
    return achievements.achievements_for(user_id, field.id, titles)


@router.get("/{user_id}/analytics")
def get_analytics(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """The student-facing half of learning_engine/analytics.py: progress,
    time spent, competencies, strengths/weaknesses, and a recommendation —
    gated by require_owner like every other per-user endpoint here.

    The admin-facing half (analytics.field_summary — most-failed questions,
    aggregate competency/completion stats across every student in a field)
    is deliberately NOT exposed as an HTTP endpoint: this app has no admin-
    role concept anywhere (see backend/auth.py — only require_owner, a
    per-resource ownership check), so an open route for it would leak every
    student's aggregate performance data to anyone who could reach the URL.
    The function itself is real, tested, and ready to wire up the moment
    real admin authentication exists — shipping it behind no access control
    just to check a box would be a security hole, not a feature."""
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])
    titles = _course_titles_for(field.id, level)
    return analytics.student_summary(user_id, field.id, list(titles.keys()), titles)


@router.get("/{user_id}/profile")
def get_student_profile(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """The unified Learning Intelligence dashboard — see learning_engine/
    student_profile.py's profile_summary for exactly which existing data
    each field maps back to (nothing here is tracked twice). No longer
    404s without an Academy enrollment: goals, learning style, language
    competencies, and the risk/motivation signals are all real without
    one — only the Academy-specific fields (strengths/weaknesses,
    frequent mistakes, learning velocity) go empty instead of populated."""
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    field_id = None
    if row:
        field = academy.get_field(row["field_id"])
        field_id = field.id if field else None
    return student_profile.profile_summary(user_id, field_id, user.interests)


class SetCareerGoalRequest(BaseModel):
    goal: str


@router.patch("/{user_id}/profile/goal")
def set_career_goal(user_id: str, payload: SetCareerGoalRequest, session: dict = Depends(auth.require_owner)) -> dict:
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    student_profile.set_career_goal(user_id, payload.goal)
    return {"career_goal": student_profile.get_career_goal(user_id)}


@router.get("/{user_id}/goals")
def get_goals(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    """Multiple, ordered learning goals (learning_engine/goals.py) — not
    tied to any one field, since a student's goals can span the whole
    platform ("pasar el B2 de inglés", "terminar la especialización en
    IA"), unlike the single per-enrollment career_goal above."""
    get_user_by_id_or_404(user_id)
    return goals.list_goals(user_id)


class AddGoalRequest(BaseModel):
    text: str


@router.post("/{user_id}/goals")
def add_goal(user_id: str, payload: AddGoalRequest, session: dict = Depends(auth.require_owner)) -> dict:
    get_user_by_id_or_404(user_id)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="El objetivo no puede estar vacío")
    return goals.add_goal(user_id, payload.text)


class UpdateGoalRequest(BaseModel):
    completed: bool = True


@router.patch("/{user_id}/goals/{goal_id}")
def update_goal(
    user_id: str, goal_id: int, payload: UpdateGoalRequest, session: dict = Depends(auth.require_owner)
) -> dict:
    get_user_by_id_or_404(user_id)
    if not goals.complete_goal(user_id, goal_id, payload.completed):
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    return {"id": goal_id, "completed": payload.completed}


@router.delete("/{user_id}/goals/{goal_id}")
def delete_goal(user_id: str, goal_id: int, session: dict = Depends(auth.require_owner)) -> dict:
    get_user_by_id_or_404(user_id)
    if not goals.remove_goal(user_id, goal_id):
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    return {"deleted": True}


@router.post("/{user_id}/goals/{goal_id}/milestones")
async def get_goal_milestones(user_id: str, goal_id: int, session: dict = Depends(auth.require_owner)) -> dict:
    """Breaks the goal into ordered milestones the first time this is
    called (mentor_engine/goal_planner.py) — generated once, persisted,
    and returned as-is on every later call for the same goal."""
    get_user_by_id_or_404(user_id)
    try:
        milestones = await goal_planner.ensure_milestones(user_id, goal_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    return {"goal_id": goal_id, "milestones": milestones}


@router.patch("/{user_id}/goals/{goal_id}/milestones/advance")
def advance_goal_milestone(user_id: str, goal_id: int, session: dict = Depends(auth.require_owner)) -> dict:
    get_user_by_id_or_404(user_id)
    updated = goals.advance_milestone(user_id, goal_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    return updated


@router.get("/{user_id}/concepts/review")
def get_concept_review(user_id: str, session: dict = Depends(auth.require_owner)) -> list[dict]:
    """Due academic-concept flashcards (term + definition) — see
    learning_engine/concept_review.py. No AI call: content already exists
    from when the concept was added to the knowledge graph."""
    get_user_by_id_or_404(user_id)
    return concept_review.due_concepts(user_id)


class ConceptReviewAnswerRequest(BaseModel):
    vocab_key: str  # as returned by get_concept_review, e.g. "academic:course-id::term-slug"
    correct: bool


@router.post("/{user_id}/concepts/review/answer")
def submit_concept_review_answer(
    user_id: str, payload: ConceptReviewAnswerRequest, session: dict = Depends(auth.require_owner)
) -> dict:
    get_user_by_id_or_404(user_id)
    if not concept_review.is_concept_vocab_key(payload.vocab_key):
        raise HTTPException(status_code=400, detail="vocab_key inválido")
    concept_id = concept_review.concept_id_from_vocab_key(payload.vocab_key)
    concept = knowledge_graph.get_concept(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concepto no encontrado")
    schedule = concept_review.record_answer(user_id, concept_id, payload.correct, concept["term"], concept["definition"])
    return {"srs": schedule}


@router.get("/{user_id}/portfolio")
def get_portfolio(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Automatic professional portfolio — every submitted assignment,
    resolved practice scenario, and completed course across every field
    the student has ever studied (see learning_engine/portfolio.py)."""
    get_user_by_id_or_404(user_id)
    data = portfolio.get_portfolio(user_id)
    all_course_ids = (
        [a["course_id"] for a in data["assignments"]]
        + [s["course_id"] for s in data["scenarios"]]
        + [c["course_id"] for c in data["completed_courses"]]
    )
    titles = _resolve_titles_for_course_ids(all_course_ids)
    for group in ("assignments", "scenarios", "completed_courses"):
        for item in data[group]:
            item["course_title"] = titles.get(item["course_id"], item["course_id"])
    return data
