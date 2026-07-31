"""University-prep academy: self-paced, accelerated study tracks across ~30
academic fields. Curriculum outlines and course content are generated once
per (field, level[, course]) and cached — see hf_client.generate_curriculum
and generate_course_content. This is explicitly NOT an accredited program;
every response that reaches the UI is meant to be shown next to a persistent
disclaimer (enforced in the frontend, not here)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import academy, auth, db, personas
from ..hf_client import hf_client
from ..models import (
    AcademicField,
    AcademicLevel,
    AcademyEnrollment,
    AcademyProgress,
    Curriculum,
    CourseContent,
    CourseStub,
    FacultyByline,
    OERSourceCitation,
    PersonaInfo,
)
from .users import get_user_by_id_or_404

router = APIRouter(prefix="/api/academy", tags=["academy"])


@router.get("/fields", response_model=list[AcademicField])
def get_fields() -> list[AcademicField]:
    return academy.all_fields()


@router.get("/fields/{field_id}/faculty", response_model=PersonaInfo)
def get_field_faculty(field_id: str) -> PersonaInfo:
    field = academy.get_field(field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    return personas.to_persona_info(personas.build_field_faculty(field))


def _course_id(field_id: str, level: AcademicLevel, order: int) -> str:
    return f"{field_id}:{level.value}:{order}"


async def _load_curriculum(user_id: str, field: AcademicField, level: AcademicLevel, native_lang: str) -> Curriculum:
    raw_courses = await hf_client.generate_curriculum(field, level, native_lang)
    courses = [
        CourseStub(id=_course_id(field.id, level, i), order=i, title=c["title"], description=c["description"])
        for i, c in enumerate(raw_courses)
    ]
    return Curriculum(field_id=field.id, field_name=field.name, level=level, level_label=level.label_es, courses=courses)


def _get_enrollment_row(user_id: str) -> Any:
    with db.cursor() as cur:
        cur.execute("SELECT field_id, level, enrolled_at FROM academy_enrollment WHERE user_id=?", (user_id,))
        return cur.fetchone()


class EnrollRequest(BaseModel):
    field_id: str
    level: AcademicLevel


@router.post("/{user_id}/enroll", response_model=AcademyEnrollment)
def enroll(user_id: str, payload: EnrollRequest, session: dict = Depends(auth.require_owner)) -> AcademyEnrollment:
    get_user_by_id_or_404(user_id)
    field = academy.get_field(payload.field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")

    enrolled_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET field_id=excluded.field_id, level=excluded.level, "
            "enrolled_at=excluded.enrolled_at",
            (user_id, field.id, payload.level.value, enrolled_at),
        )
    return AcademyEnrollment(field_id=field.id, field_name=field.name, level=payload.level,
                              level_label=payload.level.label_es, enrolled_at=enrolled_at)


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

    enrollment = AcademyEnrollment(
        field_id=field.id, field_name=field.name, level=level, level_label=level.label_es,
        enrolled_at=row["enrolled_at"],
    )
    curriculum = await _load_curriculum(user_id, field, level, user.native_lang)

    with db.cursor() as cur:
        cur.execute("SELECT course_id FROM academy_course_progress WHERE user_id=?", (user_id,))
        completed = [r["course_id"] for r in cur.fetchall()]

    return AcademyProgress(enrollment=enrollment, completed_course_ids=completed, total_courses=len(curriculum.courses))


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
    return await _load_curriculum(user_id, field, level, user.native_lang)


@router.get("/{user_id}/courses/{course_id}", response_model=CourseContent)
async def get_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseContent:
    user = get_user_by_id_or_404(user_id)
    row = _get_enrollment_row(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aún no te has inscrito en una carrera")
    field = academy.get_field(row["field_id"])
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")
    level = AcademicLevel(row["level"])

    curriculum = await _load_curriculum(user_id, field, level, user.native_lang)
    stub = next((c for c in curriculum.courses if c.id == course_id), None)
    if not stub:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    result = await hf_client.generate_course_content(field, level, stub.id, stub.title, stub.description, user.native_lang)
    return CourseContent(
        id=stub.id,
        title=stub.title,
        modules=[{"title": m["title"], "content": m["content"]} for m in result["modules"]],
        sources=[OERSourceCitation(**s) for s in result.get("sources", [])],
        faculty=FacultyByline(**result["faculty"]) if result.get("faculty") else None,
    )


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
