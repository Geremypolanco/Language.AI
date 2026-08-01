"""University-prep academy: self-paced, accelerated study tracks across ~30
academic fields. Curriculum outlines and course content are generated once
per (field, level[, course]) and cached — see hf_client.generate_curriculum
and generate_course_content. This is explicitly NOT an accredited program;
every response that reaches the UI is meant to be shown next to a persistent
disclaimer (enforced in the frontend, not here)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import academy, auth, db
from ..hf_client import hf_client
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


async def _load_curriculum(field: AcademicField, level: AcademicLevel, content_lang: str) -> Curriculum:
    raw_courses = await hf_client.generate_curriculum(field, level, content_lang)
    courses = [
        CourseStub(id=_course_id(field.id, level, i), order=i, title=c["title"], description=c["description"])
        for i, c in enumerate(raw_courses)
    ]
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
    try:
        curriculum = await _load_curriculum(field, level, content_lang)
        total_courses = len(curriculum.courses)
    except Exception:
        # generate_curriculum does live arXiv/Wikipedia/AI calls on first
        # request (nothing cached yet) — any of those failing shouldn't 500
        # the whole progress page. Fall back to the level's nominal course
        # count so the UI still has something sane to show.
        logger.exception("Curriculum generation failed for %s/%s", field.id, level.value)
        total_courses = level.course_count

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
    return await _load_curriculum(field, level, row["content_lang"] or user.native_lang)


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

    curriculum = await _load_curriculum(field, level, content_lang)
    stub = next((c for c in curriculum.courses if c.id == course_id), None)
    if not stub:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return user, field, level, stub, content_lang


@router.get("/{user_id}/courses/{course_id}", response_model=CourseContent)
async def get_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseContent:
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    modules_raw = await hf_client.generate_course_content(field, level, stub.id, stub.title, stub.description, content_lang)
    return CourseContent(id=stub.id, title=stub.title, modules=[{"title": m["title"], "content": m["content"]} for m in modules_raw])


@router.get("/{user_id}/courses/{course_id}/scenario")
async def get_practice_scenario(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """A realistic, hands-on case/scenario for this course — the practical
    complement to the theory in get_course, for fields (nursing, engineering,
    business, ...) where reading alone isn't enough."""
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    scenario = await hf_client.generate_practice_scenario(field, level, stub.id, stub.title, stub.description, content_lang)
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
    practice scenario. Submission status/feedback/grade persist per user."""
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    raw = await hf_client.generate_assignments(field, level, stub.id, stub.title, stub.description, content_lang)
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
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    raw = await hf_client.generate_assignments(field, level, stub.id, stub.title, stub.description, content_lang)
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


@router.post("/{user_id}/courses/{course_id}/complete", response_model=AcademyProgress)
async def complete_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> AcademyProgress:
    get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")

    completed_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, course_id) DO NOTHING",
            (user_id, course_id, completed_at),
        )
    return await get_progress(user_id, session)
