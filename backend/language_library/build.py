"""The build pipeline: turns curriculum.py's unit definitions into a
permanently persisted, versioned library for a given set of language pairs
— this is what scripts/build_languages.py drives.

    for each (target_lang, native_lang) pair
      for each CEFR level
        for each unit
          -> generate exercises (interests=[], recent_mistakes=[])
          -> validate, retry on failure (language_library.generators)
          -> wrap with the same teaching-intro cards the on-demand path
             has always added (hf_client._with_teaching_intros)
          -> derive a flashcard set from the un-wrapped exercises
          -> save both to the AcademyStore
        -> only after every unit at this (pair, level) saves successfully,
           flip that (pair, level)'s "latest" version pointer

Unlike academy_library.build (which iterates a fixed, enumerable catalog
of ~60 fields), there is no "all languages" to enumerate here — curriculum
content is language-agnostic, filled in by the model for whatever
target_lang/native_lang pair a real user actually picks at onboarding.
scripts/build_languages.py takes explicit --target-langs/--native-langs
instead of defaulting to "everything."

Resumable (skips a unit already saved in the target version unless
--force) and scoped per (language pair, level) — regenerating one pair's
content never touches or re-versions any other pair, matching "si una
lección cambia, regenerar únicamente esa lección."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclass_field

from .. import curriculum
from ..ai import asset_pipeline
from ..models import CEFRLevel
from . import generators
from .generators import GenerationError
from .storage import language_pair_key

logger = logging.getLogger("lingua.language_library.build")


@dataclass
class BuildReport:
    language_pair: str
    level: str
    version: str
    units_attempted: int = 0
    units_built: int = 0
    failures: list[tuple[str, str]] = dataclass_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


async def build_language_level(
    store, target_lang: str, native_lang: str, level: CEFRLevel, version: str, force: bool = False
) -> BuildReport:
    pair_key = language_pair_key(target_lang, native_lang)
    report = BuildReport(language_pair=pair_key, level=level.value, version=version)
    units = curriculum.units_for_level(level)
    report.units_attempted = len(units)

    for unit in units:
        if not force and store.load_course_asset(pair_key, level.value, unit.id, "content", version=version):
            report.units_built += 1
            continue
        try:
            raw_exercises = await generators.generate_unit_exercises(unit, target_lang, native_lang)
        except GenerationError as exc:
            report.failures.append((unit.id, str(exc)))
            logger.error("Build failed for %s/%s unit %s: %s", pair_key, level.value, unit.id, exc)
            continue

        final_exercises = generators.wrap_with_teaching_intros(raw_exercises)
        store.save_course_asset(
            pair_key, level.value, version, unit.id, "content", [e.model_dump() for e in final_exercises]
        )
        flashcards = generators.build_flashcards(raw_exercises)
        # Offline Voice Builder: pronounce every flashcard once, at build
        # time, and store the audio permanently alongside it — see
        # backend/ai/asset_pipeline.py.
        flashcards = await asset_pipeline.add_flashcard_audio(
            f"flashcards:{pair_key}:{level.value}:{unit.id}", target_lang, flashcards
        )
        store.save_course_asset(pair_key, level.value, version, unit.id, "flashcards", flashcards)
        report.units_built += 1

    if report.ok:
        store.set_latest_version(pair_key, level.value, version)
    return report


def next_version(store, pair_key: str, level: str) -> str:
    """v1, v2, v3, ... per (language pair, level) — a pair/level that
    changes only bumps its own version; nothing else in the library is
    touched (see scripts/build_languages.py's --target-langs/--native-langs
    for scoping a rebuild to just the changed pair)."""
    current = store.get_latest_version(pair_key, level)
    if current is None:
        return "v1"
    try:
        n = int(current.lstrip("v"))
    except ValueError:
        return "v1"
    return f"v{n + 1}"


async def build_all(
    store,
    language_pairs: list[tuple[str, str]],
    levels: list[CEFRLevel],
    version: str | None = None,
    force: bool = False,
) -> list[BuildReport]:
    """Builds every (language pair, level) combination given. `version`
    pins all of them to the same explicit tag when given; left as None
    (the normal case), each independently gets its own next_version()."""
    reports = []
    for target_lang, native_lang in language_pairs:
        pair_key = language_pair_key(target_lang, native_lang)
        for level in levels:
            resolved_version = version or next_version(store, pair_key, level.value)
            logger.info("Building %s / %s (version=%s)...", pair_key, level.value, resolved_version)
            report = await build_language_level(store, target_lang, native_lang, level, resolved_version, force=force)
            reports.append(report)
    return reports
