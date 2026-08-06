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
          -> synthesize + permanently store audio for every vocab_intro/
             listen_type exercise (see _attach_audio) — the two exercise
             types with an "Escuchar" button in the frontend — so that
             button's audio_url is already baked into the persisted
             exercise and playing it during a lesson never has to call a
             TTS provider at all, same "never generate during learning"
             principle already applied to the exercise text itself.
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
from ..hf_client import hf_client
from ..models import CEFRLevel, Exercise, ExerciseType
from . import generators
from .generators import GenerationError
from .storage import language_pair_key

logger = logging.getLogger("lingua.language_library.build")

# The only two exercise types the frontend ever puts an "Escuchar" button
# next to (see frontend/client/src/components/ExercisePlayer.tsx) — no
# point spending a TTS call+permanent file on a multiple_choice/fill_blank
# exercise nothing in the UI will ever play back.
_AUDIBLE_TYPES = {ExerciseType.VOCAB_INTRO, ExerciseType.LISTEN_TYPE}


async def _attach_audio(exercises: list[Exercise], target_lang: str, pair_key: str, unit_id: str) -> None:
    """Synthesizes and permanently stores audio for every audible exercise
    in place (sets .audio_url), skipping any that already has one — same
    resumability contract as build_language_level's own unit-level skip.
    A synthesis failure here is logged and left with an empty audio_url
    rather than failing the whole unit build: a lesson with 8 working
    audio clips and 1 silent "Escuchar" button is still worth publishing,
    matching how a single unit's build failure doesn't block every other
    unit in build_language_level."""
    for ex in exercises:
        if ex.type not in _AUDIBLE_TYPES or ex.audio_url:
            continue
        result = await hf_client.text_to_speech(ex.audio_text or ex.target_text, target_lang)
        if result is None:
            logger.warning(
                "Audio synthesis failed for %s/%s exercise %s (vocab_key=%s) — publishing without audio_url",
                pair_key, unit_id, ex.id, ex.vocab_key,
            )
            continue
        _audio_bytes, _media_type, filename = result
        ex.audio_url = f"/api/audio/{filename}"


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
        await _attach_audio(final_exercises, target_lang, pair_key, unit.id)
        store.save_course_asset(
            pair_key, level.value, version, unit.id, "content", [e.model_dump() for e in final_exercises]
        )
        flashcards = generators.build_flashcards(raw_exercises)
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


async def backfill_audio(store, target_lang: str, native_lang: str, level: CEFRLevel) -> BuildReport:
    """One-time migration path for content published before audio pre-
    generation existed (see _attach_audio): adds audio_url to every
    vocab_intro/listen_type exercise in the *currently published* version
    of this (pair, level) that's missing one, re-saving it under that same
    version — no text is regenerated and no new version is created,
    because nothing about the exercise content itself changed. A brand-new
    build never needs this; build_language_level already attaches audio as
    part of publishing. Returns a BuildReport with a failure recorded for
    a level that isn't published at all (nothing to backfill onto)."""
    pair_key = language_pair_key(target_lang, native_lang)
    version = store.get_latest_version(pair_key, level.value)
    report = BuildReport(language_pair=pair_key, level=level.value, version=version or "(unbuilt)")
    if version is None:
        report.failures.append(("*", "level has no published version to backfill audio onto"))
        return report

    units = curriculum.units_for_level(level)
    report.units_attempted = len(units)
    for unit in units:
        raw = store.load_course_asset(pair_key, level.value, unit.id, "content", version=version)
        if raw is None:
            report.failures.append((unit.id, "unit not found in published version"))
            continue
        exercises = [Exercise(**item) for item in raw]
        before = [e.audio_url for e in exercises]
        await _attach_audio(exercises, target_lang, pair_key, unit.id)
        if [e.audio_url for e in exercises] != before:
            store.save_course_asset(
                pair_key, level.value, version, unit.id, "content", [e.model_dump() for e in exercises]
            )
        report.units_built += 1
    return report


async def backfill_audio_all(
    store, language_pairs: list[tuple[str, str]], levels: list[CEFRLevel]
) -> list[BuildReport]:
    """backfill_audio for every (language pair, level) combination given —
    the batch entry point scripts/build_languages.py's --audio-only uses."""
    reports = []
    for target_lang, native_lang in language_pairs:
        for level in levels:
            logger.info("Backfilling audio for %s:%s / %s...", target_lang, native_lang, level.value)
            reports.append(await backfill_audio(store, target_lang, native_lang, level))
    return reports
