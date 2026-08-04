"""The build pipeline: turns academic fields into a permanently persisted,
versioned library — this is what build_academy.py (repo root) drives.

    for each academic field
      -> generate curriculum
      -> for each course
           -> generate module content, glossary, quiz, final exam,
              assignments, practice scenario
           -> validate each one (academy_library.validators)
           -> save to the AcademyStore
    -> only after every course in a (field, level) saves successfully,
       flip that field/level's "latest" pointer to the new version

No manual intervention required for a full run: build_academy.py iterates
every field/level with no per-item confirmation, and a transient failure on
one course doesn't abort the run — it's recorded in the returned BuildReport
and the rest of the build continues, so one bad course never blocks
publishing everything else that succeeded.

Specializations (AcademicField.base_field_id set) only generate their own
additional advanced courses here, not the base field's foundational ones —
see _course_count_for. The served curriculum for a specialization (see
routers/academy.py) prepends the base field's already-built courses ahead
of the specialization's own, so the shared content is never generated (or
stored) twice.

Content-type scope, deliberately: this generates curriculum + modules +
glossary + quiz + a final exam + assignments (tarea/informe/proyecto,
covering the "project"/"report"/"homework" asks) + one practice scenario
per course. Labs, a separate midterm (generators.generate_exam already
accepts exam_kind="midterm" — just not called here yet), bibliography,
and raw source-code/pseudocode blocks are NOT generated in this pass; adding
any of them is "write one more generators.generate_x + validators.validate_x
following the existing pattern, then one more save_course_asset call below"
— not a redesign — but doing all of them for every course across every
field in one shot would multiply this build's already-substantial AI-token
cost several times over for content types that matter less than getting the
core teaching material (modules/glossary/quiz/exam/assignments) built and
validated first.
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
    from ..models import AcademicField

logger = logging.getLogger("lingua.academy_library.build")

# How many of a specialization's own (non-shared) courses to generate, on
# top of whatever its base field already has built — see this module's
# docstring. Deliberately smaller than a full level's course_count, since a
# specialization is meant to be the "advanced extra courses" layer, not a
# second full curriculum duplicating the base field's foundations.
SPECIALIZATION_COURSE_COUNT = 5

_ASSET_KINDS = ("content", "glossary", "quiz", "exam", "assignments", "scenario")


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


def _course_id(field_id: str, level: AcademicLevel, order: int) -> str:
    return f"{field_id}:{level.value}:{order}"


async def build_field_level(
    store: AcademyStore,
    field: "AcademicField",
    level: AcademicLevel,
    native_lang: str,
    version: str,
    force: bool = False,
) -> BuildReport:
    report = BuildReport(field_id=field.id, level=level.value, version=version)
    course_count = _course_count_for(field, level)

    curriculum = None if force else store.load_curriculum(field.id, level.value, version=version)
    if curriculum is None:
        try:
            curriculum = await generators.generate_curriculum(field, level, native_lang, course_count)
        except GenerationError as exc:
            report.failures.append((f"{field.id}:curriculum", str(exc)))
            logger.error("Curriculum build failed for %s/%s: %s", field.id, level.value, exc)
            return report
        store.save_curriculum(field.id, level.value, version, curriculum)

    for i, course in enumerate(curriculum["courses"]):
        course_id = _course_id(field.id, level, i)
        title, description = course["title"], course["description"]
        report.courses_attempted += 1
        course_ok = True

        for kind in _ASSET_KINDS:
            if not force and store.load_course_asset(field.id, level.value, course_id, kind, version=version):
                continue  # resumable: a re-run of the same version skips work already done
            try:
                if kind == "content":
                    data = await generators.generate_course_content(field, level, title, description, native_lang)
                elif kind == "glossary":
                    data = await generators.generate_glossary(field, level, title, description, native_lang)
                elif kind == "quiz":
                    data = await generators.generate_quiz(field, level, title, description, native_lang)
                elif kind == "exam":
                    data = await generators.generate_exam(field, level, title, description, native_lang)
                elif kind == "assignments":
                    data = await generators.generate_assignments(field, level, course_id, title, description, native_lang)
                else:  # scenario
                    data = await generators.generate_scenario(field, level, title, description, native_lang)
            except GenerationError as exc:
                course_ok = False
                report.failures.append((f"{course_id}:{kind}", str(exc)))
                logger.error("Build failed for %s (%s): %s", course_id, kind, exc)
                continue
            store.save_course_asset(field.id, level.value, version, course_id, kind, data)

        if course_ok:
            report.courses_built += 1

    if report.ok:
        store.set_latest_version(field.id, level.value, version)
    return report


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
