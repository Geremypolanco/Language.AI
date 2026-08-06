"""The build pipeline: turns academic fields into a permanently persisted,
versioned library. Driven three ways now: scripts/build_academy.py (a
manual, forced/one-off rebuild of specific fields), academy_library.
proactive_builder (an automatic background loop that builds the whole
catalog ahead of time — the primary mechanism in production), and
academy_library.auto_build (a bounded, synchronous on-demand safety net for
whatever the proactive builder hasn't reached yet). All three call the same
functions below — this module has no idea which one is calling it.

    for each academic field
      -> generate curriculum
      -> for each course (build_course)
           -> generate module content, glossary, quiz, final exam,
              assignments, practice scenario, educational metadata
           -> validate each one (academy_library.validators)
           -> save to the AcademyStore
    -> only after every ATTEMPTED course in a (field, level) saves
       successfully, flip that field/level's "latest" pointer to the new
       version (see max_courses: a fast-path call attempting just course 0
       can still safely flip latest for a real, if partial, curriculum)
    -> separately, build_field_biography: one tutor biography per field
       (not per level — a professor teaches across all three)

No manual intervention required for a full run: every driver above iterates
with no per-item confirmation, and a transient failure on one course doesn't
abort the run — it's recorded in the returned BuildReport (or build_course's
own failure list) and the rest of the build continues, so one bad course
never blocks publishing everything else that succeeded.

Specializations (AcademicField.base_field_id set) only generate their own
additional advanced courses here, not the base field's foundational ones —
see _course_count_for. The served curriculum for a specialization (see
routers/academy.py) prepends the base field's already-built courses ahead
of the specialization's own, so the shared content is never generated (or
stored) twice.

Content-type scope, deliberately: this generates curriculum + modules +
glossary + quiz + a final exam + assignments (tarea/informe/proyecto,
covering the "project"/"report"/"homework" asks) + one practice scenario +
educational metadata (learning objectives, Bloom level, estimated hours,
...) per course, plus one tutor biography per field. Labs, a separate
midterm (generators.generate_exam already accepts exam_kind="midterm" —
just not called here yet), bibliography, and raw source-code/pseudocode
blocks are NOT generated in this pass; adding any of them is "write one
more generators.generate_x + validators.validate_x following the existing
pattern, then one more save_course_asset call in build_course" — not a
redesign — but doing all of them for every course across every field in one
shot would multiply this build's already-substantial AI-token cost several
times over for content types that matter less than getting the core
teaching material built and validated first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclass_field
from typing import TYPE_CHECKING

from .. import academy
from ..models import AcademicLevel
from . import generators
from .generators import GenerationError
from .storage import AcademyStore

if TYPE_CHECKING:
    from ..models import AcademicField, CEFRLevel

logger = logging.getLogger("lingua.academy_library.build")

# How many of a specialization's own (non-shared) courses to generate, on
# top of whatever its base field already has built — see this module's
# docstring. Deliberately smaller than a full level's course_count, since a
# specialization is meant to be the "advanced extra courses" layer, not a
# second full curriculum duplicating the base field's foundations.
SPECIALIZATION_COURSE_COUNT = 5

# "metadata" (Curriculum Engine Phase 1: learning objectives, Bloom level,
# estimated hours, difficulty, ...) generates from the SAME title/description
# every other asset kind already uses — one extra AI call per course, not a
# second pass over the whole pipeline.
_ASSET_KINDS = ("content", "glossary", "quiz", "exam", "assignments", "scenario", "metadata")


@dataclass
class BuildReport:
    field_id: str
    level: str
    version: str
    courses_attempted: int = 0
    courses_built: int = 0
    failures: list[tuple[str, str]] = dataclass_field(default_factory=list)  # (course_id:kind, error)

    @property
    def ok(self) -> bool:
        return not self.failures


def _course_count_for(field: "AcademicField", level: AcademicLevel) -> int:
    return SPECIALIZATION_COURSE_COUNT if field.base_field_id else level.course_count


def course_id_for(field_id: str, level: AcademicLevel, order: int) -> str:
    return f"{field_id}:{level.value}:{order}"


# Backwards-compatible alias — routers/academy.py used to keep its own copy
# of this exact function under this name; kept so nothing else needs to
# change just to import the shared one.
_course_id = course_id_for


async def build_course(
    store: AcademyStore,
    field: "AcademicField",
    level: AcademicLevel,
    version: str,
    course_id: str,
    title: str,
    description: str,
    native_lang: str,
    force: bool = False,
    cefr_level: "CEFRLevel | None" = None,
) -> list[tuple[str, str]]:
    """Builds every still-missing asset kind for ONE course (resumable:
    skips a kind already saved under this version unless force=True) and
    persists each successful one immediately. Returns a list of (kind,
    error) for whatever failed — empty means every kind saved. Extracted
    from build_field_level's per-course loop so the proactive builder and
    the on-demand auto-build safety net can build a single course without
    re-implementing this resumable-skip logic."""
    failures: list[tuple[str, str]] = []
    for kind in _ASSET_KINDS:
        if not force and store.load_course_asset(field.id, level.value, course_id, kind, version=version):
            continue  # resumable: a re-run of the same version skips work already done
        try:
            if kind == "content":
                data = await generators.generate_course_content(field, level, title, description, native_lang, cefr_level)
            elif kind == "glossary":
                data = await generators.generate_glossary(field, level, title, description, native_lang, cefr_level=cefr_level)
            elif kind == "quiz":
                data = await generators.generate_quiz(field, level, title, description, native_lang, cefr_level=cefr_level)
            elif kind == "exam":
                data = await generators.generate_exam(field, level, title, description, native_lang, cefr_level=cefr_level)
            elif kind == "assignments":
                data = await generators.generate_assignments(field, level, course_id, title, description, native_lang, cefr_level=cefr_level)
            elif kind == "scenario":
                data = await generators.generate_scenario(field, level, title, description, native_lang, cefr_level=cefr_level)
            else:  # metadata
                data = await generators.generate_course_metadata(field, level, title, description, native_lang)
        except GenerationError as exc:
            failures.append((kind, str(exc)))
            logger.error("Build failed for %s (%s): %s", course_id, kind, exc)
            continue
        store.save_course_asset(field.id, level.value, version, course_id, kind, data)
    return failures


async def build_field_level(
    store: AcademyStore,
    field: "AcademicField",
    level: AcademicLevel,
    native_lang: str,
    version: str,
    force: bool = False,
    max_courses: int | None = None,
    cefr_level: "CEFRLevel | None" = None,
) -> BuildReport:
    """Builds a whole (field, level): curriculum shell, then every course's
    assets via build_course(). `max_courses` caps how many courses are
    actually attempted this call (used by the proactive builder's/auto-
    build's fast path to build just the curriculum + first course quickly,
    leaving the rest for a later resumed call) — report.ok/the "flip
    latest" gate below only ever evaluates the attempted subset, so a
    max_courses=1 call that succeeds still safely publishes a real,
    servable (if partial) curriculum; a later call with max_courses=None
    (or a higher cap) resumes and completes the remaining courses, skipping
    everything build_course already saved."""
    report = BuildReport(field_id=field.id, level=level.value, version=version)
    course_count = _course_count_for(field, level)

    curriculum = None if force else store.load_curriculum(field.id, level.value, version=version)
    if curriculum is None:
        try:
            curriculum = await generators.generate_curriculum(field, level, native_lang, course_count, cefr_level)
        except GenerationError as exc:
            report.failures.append((f"{field.id}:curriculum", str(exc)))
            logger.error("Curriculum build failed for %s/%s: %s", field.id, level.value, exc)
            return report
        store.save_curriculum(field.id, level.value, version, curriculum)

    courses = curriculum["courses"]
    if max_courses is not None:
        courses = courses[:max_courses]

    for i, course in enumerate(courses):
        course_id = course_id_for(field.id, level, i)
        title, description = course["title"], course["description"]
        report.courses_attempted += 1

        failures = await build_course(store, field, level, version, course_id, title, description, native_lang, force, cefr_level)
        for kind, error in failures:
            report.failures.append((f"{course_id}:{kind}", error))
        if not failures:
            report.courses_built += 1

    if report.ok:
        store.set_latest_version(field.id, level.value, version)
    return report


async def build_field_biography(
    store: AcademyStore, field: "AcademicField", native_lang: str, force: bool = False,
) -> bool:
    """One tutor biography per field, independent of level (a professor
    teaches across ASSOCIATE/BACHELOR/MASTER alike — see backend/
    personas.py) — skipped if already persisted unless force=True. Returns
    True if a biography exists in the store after this call (whether it
    was already there or just built)."""
    if not force and store.load_field_biography(field.id) is not None:
        return True
    try:
        bio = await generators.generate_tutor_biography(field, native_lang)
    except GenerationError as exc:
        logger.error("Tutor biography build failed for %s: %s", field.id, exc)
        return False
    store.save_field_biography(field.id, bio)
    return True


def next_version(store: AcademyStore, field_id: str, level: str) -> str:
    """v1, v2, v3, ... per (field, level) — matches the versioning example
    in the refactor request: each field tracks its OWN version number,
    bumped only when that field is rebuilt. A field that changes only
    regenerates itself (see build_academy.py's --fields flag); nothing else
    in the library is touched or re-versioned."""
    current = store.get_latest_version(field_id, level)
    if current is None:
        return "v1"
    try:
        n = int(current.lstrip("v"))
    except ValueError:
        return "v1"
    return f"v{n + 1}"


async def build_all(
    store: AcademyStore,
    fields: list["AcademicField"],
    levels: list[AcademicLevel],
    native_lang: str,
    version: str | None = None,
    force: bool = False,
) -> list[BuildReport]:
    """Builds every (field, level) pair. `version` pins every one of them to
    the same explicit version string when given (e.g. a coordinated release
    tag, or for deterministic tests); left as None (the normal case), each
    (field, level) independently gets its own next_version() — one field
    changing never bumps or touches any other field's version."""
    reports = []
    for field in fields:
        for level in levels:
            resolved_version = version or next_version(store, field.id, level.value)
            logger.info("Building %s / %s (version=%s)...", field.id, level.value, resolved_version)
            report = await build_field_level(store, field, level, native_lang, resolved_version, force=force)
            reports.append(report)
    return reports


def resolve_fields(field_ids: list[str] | None) -> list["AcademicField"]:
    if not field_ids:
        return academy.all_fields()
    resolved = []
    for fid in field_ids:
        f = academy.get_field(fid)
        if f is None:
            raise ValueError(f"unknown academic field id: {fid!r}")
        resolved.append(f)
    return resolved
