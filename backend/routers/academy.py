"""University-prep academy: self-paced, accelerated study tracks across ~60
academic fields. This is explicitly NOT an accredited program; every
response that reaches the UI is meant to be shown next to a persistent
disclaimer (enforced in the frontend, not here).

Content is served from the pre-generated, versioned library
(backend/academy_library/), which a background task
(academy_library.proactive_builder.run_periodic_academy_build, started from
main.py's lifespan) keeps building automatically for as long as the app
runs — nobody has to run scripts/build_academy.py by hand for a real
deployment anymore (that CLI still exists for a forced/one-off rebuild of a
specific field, see its own docstring). Whatever the proactive builder
hasn't reached yet for a given (field, level) is covered by
academy_library.auto_build's bounded, synchronous on-demand safety net —
see that module's docstring — so a request is never more than "the next
course's generation time" away from a real answer.

The oldest fallback layer — fully unpersisted, live generation via
hf_client.generate_curriculum/generate_course_content/... — still exists
underneath both of the above, as the last resort when every AI provider is
genuinely unreachable (or in the test suite, where AI calls are disabled
outright). That one path predates this whole library and is intentionally
never removed: it's what keeps this router honest about "never show
content unavailable" even in total-outage conditions, at the cost of not
persisting what it generates. glossary/quiz/exam never had this legacy
fallback (they're new content types with no "how it always worked" to
preserve) — they still 404 in that specific worst case, but now only after
the on-demand safety net itself has already tried and failed to build the
missing course.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import academy, auth, db
from ..academy_library import auto_build
from ..academy_library.build import course_id_for
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
    CEFRLevel,
    Curriculum,
    CourseContent,
    CourseMetadata,
    CourseStub,
    UserProfile,
)
from .users import get_user_by_id_or_404

logger = logging.getLogger("lingua.academy")

router = APIRouter(prefix="/api/academy", tags=["academy"])


@router.get("/fields", response_model=list[AcademicField])
def get_fields() -> list[AcademicField]:
    return academy.all_fields()


# Kept as a thin alias — this router used to keep its own private copy of
# this exact function; several call sites below still spell it _course_id.
_course_id = course_id_for


def _cefr_level_for(user: UserProfile, content_lang: str) -> CEFRLevel | None:
    """CEFR-aware content calibration only makes sense when content_lang IS
    the language this app actually tracks a proficiency level for — the
    learner's target_lang (see models.UserProfile.level). Any other
    content_lang (including the learner's own native_lang, the default)
    generates uncalibrated, exactly as before this existed."""
    return user.level if content_lang == user.target_lang else None


def _stubs_from_courses(
    field_id: str, level: AcademicLevel, courses: list[dict], order_offset: int = 0,
    prerequisite_edges: list[tuple[str, str]] | None = None,
) -> list[CourseStub]:
    prerequisites_of: dict[str, list[str]] = {}
    for from_id, to_id in prerequisite_edges or ():
        prerequisites_of.setdefault(to_id, []).append(from_id)
    return [
        CourseStub(
            id=_course_id(field_id, level, i), order=order_offset + i, title=c["title"], description=c["description"],
            prerequisite_ids=prerequisites_of.get(_course_id(field_id, level, i), []),
        )
        for i, c in enumerate(courses)
    ]


async def _load_curriculum(
    field: AcademicField, level: AcademicLevel, content_lang: str, cefr_level: CEFRLevel | None = None,
) -> Curriculum:
    store = get_default_store()

    # Auto-build safety net: bounded and synchronous, a no-op with zero AI
    # calls whenever a curriculum is already persisted (the normal case,
    # once the proactive builder — or a previous call here — has reached
    # this field/level). Never raises; a failure just means this falls
    # through to the legacy live-generation path below, exactly as it
    # always has. See academy_library/auto_build.py's module docstring.
    try:
        await auto_build.ensure_field_level_started(store, field, level, content_lang, cefr_level)
        if field.base_field_id:
            base_field = academy.get_field(field.base_field_id)
            if base_field:
                await auto_build.ensure_field_level_started(store, base_field, level, content_lang, cefr_level)
    except Exception:
        logger.exception("Auto-build safety net raised for %s/%s", field.id, level.value)

    persisted = store.load_curriculum(field.id, level.value)
    if persisted is not None:
        all_ids = [_course_id(field.id, level, i) for i in range(len(persisted["courses"]))]
        edges = knowledge_graph.prerequisite_edges_for(all_ids)
        courses = _stubs_from_courses(field.id, level, persisted["courses"], prerequisite_edges=edges)
        # A specialization's served curriculum prepends its base field's
        # already-built courses ahead of its own — see academy_library/
        # build.py's module docstring for why the specialization's own
        # build never regenerates (or stores a second copy of) them.
        if field.base_field_id:
            base_field = academy.get_field(field.base_field_id)
            base_persisted = store.load_curriculum(field.base_field_id, level.value) if base_field else None
            if base_field and base_persisted:
                base_ids = [_course_id(base_field.id, level, i) for i in range(len(base_persisted["courses"]))]
                base_edges = knowledge_graph.prerequisite_edges_for(base_ids)
                base_stubs = _stubs_from_courses(base_field.id, level, base_persisted["courses"], prerequisite_edges=base_edges)
                courses = base_stubs + courses
                for i, stub in enumerate(courses):
                    stub.order = i
        # Best-effort: finishes building the rest of this field/level (and
        # its base field, for a specialization) in the background —
        # deduplicated per-process, a no-op once already complete. Never
        # awaited: a curriculum read must never wait on a whole field's
        # worth of generation.
        try:
            auto_build.ensure_background_completion(store, field, level, content_lang, cefr_level)
            if field.base_field_id:
                base_field = academy.get_field(field.base_field_id)
                if base_field:
                    auto_build.ensure_background_completion(store, base_field, level, content_lang, cefr_level)
        except Exception:
            logger.exception("Failed to schedule background completion for %s/%s", field.id, level.value)
        return Curriculum(field_id=field.id, field_name=field.name, level=level, level_label=level.label_es, courses=courses)

    # Still not built (the auto-build safety net itself failed, e.g. every
    # AI provider is down, or LINGUA_TESTING disables AI outright) — same
    # on-demand, unpersisted generation this app has always used.
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


class EnrollRequest(BaseModel):
    field_id: str
    level: AcademicLevel
    # Optional — the language to study this career's content in. Defaults to
    # the learner's native_lang UNLESS they've already reached
    # academy.TARGET_LANG_CEFR_THRESHOLD in their target_lang, in which case
    # it defaults to target_lang instead (see _default_content_lang) — the
    # "Knowledge Engine" integration between the language and university
    # engines. A learner can always override this explicitly either way.
    content_lang: str | None = None


def _default_content_lang(user: UserProfile) -> str:
    if user.level.rank >= academy.TARGET_LANG_CEFR_THRESHOLD.rank:
        return user.target_lang
    return user.native_lang


@router.post("/{user_id}/enroll", response_model=AcademyEnrollment)
async def enroll(user_id: str, payload: EnrollRequest, session: dict = Depends(auth.require_owner)) -> AcademyEnrollment:
    user = get_user_by_id_or_404(user_id)
    field = academy.get_field(payload.field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Área de estudio no encontrada")

    content_lang = payload.content_lang or _default_content_lang(user)
    cefr_level = _cefr_level_for(user, content_lang)
    enrolled_at = datetime.now(UTC).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at, content_lang) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET field_id=excluded.field_id, level=excluded.level, "
            "enrolled_at=excluded.enrolled_at, content_lang=excluded.content_lang",
            (user_id, field.id, payload.level.value, enrolled_at, content_lang),
        )

    # Bounded, synchronous fast path (curriculum shell + first course) so
    # opening the curriculum right after enrolling is never a cold start —
    # a no-op with zero AI calls if the proactive builder already covered
    # this field/level (the normal case). The rest of the field finishes in
    # the background; see academy_library/auto_build.py.
    store = get_default_store()
    try:
        await auto_build.ensure_field_level_started(store, field, payload.level, content_lang, cefr_level)
        auto_build.ensure_background_completion(store, field, payload.level, content_lang, cefr_level)
    except Exception:
        logger.exception("Auto-build at enrollment failed for %s/%s", field.id, payload.level.value)

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
    cefr_level = _cefr_level_for(user, content_lang)
    enrollment = _build_enrollment(field, level, row["enrolled_at"], content_lang)
    unlocked: list[str] = []
    try:
        curriculum = await _load_curriculum(field, level, content_lang, cefr_level)
        total_courses = len(curriculum.courses)
        try:
            unlocked = sorted(knowledge_graph.unlocked_courses(user_id, [c.id for c in curriculum.courses]))
        except Exception:
            logger.exception("unlocked_courses failed for %s/%s", field.id, level.value)
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

    return AcademyProgress(
        enrollment=enrollment, completed_course_ids=completed, total_courses=total_courses, unlocked_course_ids=unlocked
    )


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
    content_lang = row["content_lang"] or user.native_lang
    return await _load_curriculum(field, level, content_lang, _cefr_level_for(user, content_lang))


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
    cefr_level = _cefr_level_for(user, content_lang)

    curriculum = await _load_curriculum(field, level, content_lang, cefr_level)
    stub = next((c for c in curriculum.courses if c.id == course_id), None)
    if not stub:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    # A specialization's curriculum can contain course ids owned by its base
    # field (see _load_curriculum) — course_id's own field_id prefix is
    # always the TRUE owner of that course's content, so library/legacy
    # lookups below must use that field, not necessarily the enrolled one.
    owning_field = academy.get_field(course_id.split(":")[0]) or field
    return user, owning_field, level, stub, content_lang, cefr_level


@router.get("/{user_id}/courses/{course_id}", response_model=CourseContent)
async def get_course(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseContent:
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    store = get_default_store()
    persisted = store.load_course_asset(field.id, level.value, course_id, "content")
    if persisted is None:
        # On-demand safety net: builds (and persists) this one course if the
        # proactive builder hasn't reached it yet. A no-op if there's no
        # persisted curriculum to build against at all (see
        # academy_library.auto_build.ensure_course_built) — falls through
        # to the fully-unpersisted legacy generator below either way.
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        persisted = store.load_course_asset(field.id, level.value, course_id, "content")
    if persisted is not None:
        return CourseContent(id=stub.id, title=stub.title, modules=persisted["modules"])
    modules_raw = await hf_client.generate_course_content(field, level, stub.id, stub.title, stub.description, content_lang)
    return CourseContent(id=stub.id, title=stub.title, modules=[{"title": m["title"], "content": m["content"]} for m in modules_raw])


async def _get_or_build_course_asset(field: AcademicField, level: AcademicLevel, course_id: str, kind: str, stub: CourseStub, content_lang: str, cefr_level: CEFRLevel | None) -> Any | None:
    """Shared persisted-or-safety-net-build lookup for the library-only
    asset kinds (glossary/quiz/exam/metadata) — these have no legacy
    unpersisted fallback (see this module's docstring), so once the safety
    net itself fails too, the caller's own 404 is the honest final answer."""
    store = get_default_store()
    data = store.load_course_asset(field.id, level.value, course_id, kind)
    if data is None:
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        data = store.load_course_asset(field.id, level.value, course_id, kind)
    return data


@router.get("/{user_id}/courses/{course_id}/glossary")
async def get_glossary(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Key terms + plain-language definitions for this course. Library-only
    — tries the on-demand safety net if not already built, and only 404s
    if that itself fails too (e.g. every AI provider is genuinely down)."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    data = await _get_or_build_course_asset(field, level, course_id, "glossary", stub, content_lang, cefr_level)
    if data is None:
        raise HTTPException(status_code=404, detail="El glosario de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/quiz")
async def get_quiz(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Library-only, like get_glossary above."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    data = await _get_or_build_course_asset(field, level, course_id, "quiz", stub, content_lang, cefr_level)
    if data is None:
        raise HTTPException(status_code=404, detail="El quiz de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/exam")
async def get_exam(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """Library-only, like get_glossary above."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    data = await _get_or_build_course_asset(field, level, course_id, "exam", stub, content_lang, cefr_level)
    if data is None:
        raise HTTPException(status_code=404, detail="El examen de este curso aún no está disponible")
    return data


@router.get("/{user_id}/courses/{course_id}/metadata", response_model=CourseMetadata)
async def get_course_metadata(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> CourseMetadata:
    """Educational metadata (learning objectives, Bloom level, estimated
    hours, difficulty, ...) — library-only, like get_glossary above."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    data = await _get_or_build_course_asset(field, level, course_id, "metadata", stub, content_lang, cefr_level)
    if data is None:
        raise HTTPException(status_code=404, detail="La metadata de este curso aún no está disponible")
    return CourseMetadata(**data)


@router.get("/{user_id}/courses/{course_id}/scenario")
async def get_practice_scenario(user_id: str, course_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    """A realistic, hands-on case/scenario for this course — the practical
    complement to the theory in get_course, for fields (nursing, engineering,
    business, ...) where reading alone isn't enough."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    store = get_default_store()
    scenario = store.load_course_asset(field.id, level.value, course_id, "scenario")
    if scenario is None:
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        scenario = store.load_course_asset(field.id, level.value, course_id, "scenario")
    if scenario is None:
        scenario = await hf_client.generate_practice_scenario(field, level, stub.id, stub.title, stub.description, content_lang)
    return {"scenario": scenario}


class SimplifyRequest(BaseModel):
    text: str
    # Defaults to the learner's own native_lang — the always-available
    # "switch language / get help" control required whenever Academy
    # content is being studied in a language the learner is still
    # acquiring (see academy.TARGET_LANG_CEFR_THRESHOLD). Never persisted:
    # this is per-learner, in-the-moment help, not shared library content.
    help_lang: str | None = None


@router.post("/{user_id}/courses/{course_id}/simplify")
async def simplify_course_text(
    user_id: str, course_id: str, payload: SimplifyRequest, session: dict = Depends(auth.require_owner)
) -> dict:
    user, _field, _level, _stub, _content_lang, cefr_level = await _resolve_course(user_id, course_id)
    help_lang = payload.help_lang or user.native_lang
    prompt = academy.build_simplify_prompt(payload.text, help_lang, cefr_level)
    try:
        explanation = await hf_client.chat([{"role": "user", "content": prompt}], max_tokens=500)
    except Exception:
        logger.exception("Simplify request failed for course %s", course_id)
        explanation = "No se pudo generar una simplificación en este momento — inténtalo de nuevo."
    return {"explanation": explanation}


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
    practice scenario. Submission status/feedback/grade persist per user."""
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    store = get_default_store()
    raw = store.load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        raw = store.load_course_asset(field.id, level.value, course_id, "assignments")
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
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    store = get_default_store()
    raw = store.load_course_asset(field.id, level.value, course_id, "assignments")
    if raw is None:
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        raw = store.load_course_asset(field.id, level.value, course_id, "assignments")
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
    _user, field, level, stub, content_lang, cefr_level = await _resolve_course(user_id, course_id)
    store = get_default_store()
    data = store.load_course_asset(field.id, level.value, course_id, kind)
    if data is None:
        # Rare in practice — GET .../quiz or .../exam already triggers the
        # on-demand safety net (see _get_or_build_course_asset), so a
        # submission almost always finds this already built. Still worth
        # one more bounded attempt here rather than a hard 404 on a
        # student's actual submission.
        await auto_build.ensure_course_built(store, field, level, course_id, stub.title, stub.description, content_lang, cefr_level)
        data = store.load_course_asset(field.id, level.value, course_id, kind)
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
            try:
                curriculum = await _load_curriculum(field, level, content_lang)
                total_courses = len(curriculum.courses)
            except Exception:
                logger.exception("Curriculum load failed for predictions on %s/%s", field.id, level.value)
                total_courses = level.course_count
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
