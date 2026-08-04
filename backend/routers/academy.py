"""University-prep academy: self-paced, accelerated study tracks across ~60
academic fields. This is explicitly NOT an accredited program; every
response that reaches the UI is meant to be shown next to a persistent
disclaimer (enforced in the frontend, not here).

Content is served from the pre-generated, versioned library
(backend/academy_library/ — built by scripts/build_academy.py) whenever it
exists, so a student's learning session never waits on an AI call. Any
(field, level) the build pipeline hasn't covered yet transparently falls
back to the legacy on-demand-generate-and-cache path (hf_client.generate_
curriculum/generate_course_content/...) — this fallback is deliberate, not
a leftover: flipping it off entirely the moment the library module shipped
would have made every one of the ~60 fields "not available" for every
learner until someone ran a very large, real-money AI build first. Once a
field is actually built, it serves instantly from disk and never touches
Hugging Face again; unbuilt fields keep working exactly as they always
have until they, too, get built. Brand-new content types this library adds
(glossary/quiz/exam) have no such legacy path — there's no "how it always
worked" to preserve for something that didn't exist before, so those
endpoints are library-only and return 404 until the course is built.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from .. import academy, auth, db
from ..academy_library.storage import get_default_store
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


def _stubs_from_courses(field_id: str, level: AcademicLevel, courses: list[dict], order_offset: int = 0) -> list[CourseStub]:
    return [
        CourseStub(id=_course_id(field_id, level, i), order=order_offset + i, title=c["title"], description=c["description"])
        for i, c in enumerate(courses)
    ]


async def _load_curriculum(field: AcademicField, level: AcademicLevel, content_lang: str) -> Curriculum:
    store = get_default_store()
    persisted = store.load_curriculum(field.id, level.value)
    if persisted is not None:
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

    # Not built yet — same on-demand generation this app has always used.
    raw_courses = await hf_client.generate_curriculum(field, level, content_lang)
    courses = _stubs_from_courses(field.id, level, raw_courses)
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


async def _prefetch_first_course(field: AcademicField, level: AcademicLevel, content_lang: str) -> None:
    """Warms the curriculum + first course's content/assignments cache
    right after enrollment — same "make the next click instant" rationale
    as lessons.py's unit prefetch, so opening the first course doesn't sit
    on an AI generation wait right when a learner has just committed to a
    field. Best-effort: a failure here just means it generates on demand
    like before, same as any cache miss."""
    try:
        curriculum = await _load_curriculum(field, level, content_lang)
        if not curriculum.courses:
            return
        first = curriculum.courses[0]
        await hf_client.generate_course_content(field, level, first.id, first.title, first.description, content_lang)
        await hf_client.generate_assignments(field, level, first.id, first.title, first.description, content_lang)
    except Exception:
        logger.exception("Background academy prefetch failed for field %s", field.id)


class EnrollRequest(BaseModel):
    field_id: str
    level: AcademicLevel
    # Optional — the language to study this career's content in. Defaults to
    # the learner's native_lang (the previous, only behavior) when omitted,
    # but a learner can pick a different one, e.g. to study in their target
    # language for extra immersion.
    content_lang: str | None = None


@router.post("/{user_id}/enroll", response_model=AcademyEnrollment)
def enroll(
    user_id: str, payload: EnrollRequest, background_tasks: BackgroundTasks, session: dict = Depends(auth.require_owner)
) -> AcademyEnrollment:
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
    background_tasks.add_task(_prefetch_first_course, field, payload.level, content_lang)
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

    # A specialization's curriculum can contain course ids owned by its base
    # field (see _load_curriculum) — course_id's own field_id prefix is
    # always the TRUE owner of that course's content, so library/legacy
    # lookups below must use that field, not necessarily the enrolled one.
    owning_field = academy.get_field(course_id.split(":")[0]) or field
    return user, owning_field, level, stub, content_lang


@router.get("/{user_id}/courses/{course_id}", response_model=CourseContent)
async def get_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseContent:
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    persisted = get_default_store().load_course_asset(field.id, level.value, course_id, "content")
    if persisted is not None:
        return CourseContent(id=stub.id, title=stub.title, modules=persisted["modules"])
    modules_raw = await hf_client.generate_course_content(field, level, stub.id, stub.title, stub.description, content_lang)
    return CourseContent(id=stub.id, title=stub.title, modules=[{"title": m["title"], "content": m["content"]} for m in modules_raw])


@router.get("/{user_id}/courses/{course_id}/glossary")
async def get_glossary(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Key terms + plain-language definitions for this course. Library-only
    — a brand-new content type with no legacy on-demand path — so this 404s
    until the course has actually been built (see backend/academy_library)."""
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
    business, ...) where reading alone isn't enough."""
    _user, field, level, stub, content_lang = await _resolve_course(user_id, course_id)
    scenario = get_default_store().load_course_asset(field.id, level.value, course_id, "scenario")
    if scenario is None:
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
    raw = get_default_store().load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
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
    raw = get_default_store().load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
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
