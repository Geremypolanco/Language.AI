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
          -> save both to the AcademyStore
          -> enqueue an "audio_unit" job (see backend/jobs/) if this unit
             has any vocab_intro/listen_type exercise still missing
             audio_url — never call the TTS provider inline here. A
             worker running inside the always-on backend process (see
             backend/jobs/worker.py) claims and executes that job
             whenever it gets to it, independent of whatever
             script/session/SSH-tunnel triggered this build. This is
             exactly what makes a large model download (e.g. Piper's
             ~100MB "high" quality English voice) unable to blow up a
             build run the way it could when audio synthesis used to
             happen synchronously, inline, right here.
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

import json
import logging
import os
from dataclasses import dataclass, field as dataclass_field

from .. import curriculum
from ..academy_library.storage import _safe_component
from ..jobs import manager as job_manager
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
_AUDIBLE_TYPE_VALUES = {t.value for t in _AUDIBLE_TYPES}


def validate_audio_bytes(data: bytes) -> list[str]:
    """The Asset Validator for the "audio_unit" job type (see backend/
    jobs/executors/audio.py, which is the only caller in the queue path —
    exported from here too since _attach_audio, the pre-queue direct-call
    convenience some tests still use, applies the same check). A WAV/FLAC/
    MP3 container's own header is already well past this many bytes; a
    file this small is a truncated download or an error page saved as if
    it were audio, not a real clip."""
    problems = []
    if len(data) < 64:
        problems.append(f"audio payload suspiciously small ({len(data)} bytes)")
    return problems


async def _attach_audio(exercises: list[Exercise], target_lang: str, pair_key: str, unit_id: str) -> None:
    """Synthesizes and permanently stores audio for every audible exercise
    in place (sets .audio_url), skipping any that already has one —
    resumable at exercise granularity: re-running this (e.g. a retried
    "audio_unit" job) only ever does the remaining work, never redoes
    what already succeeded. A synthesis failure (including a validation
    failure — see validate_audio_bytes) is logged and left with an empty
    audio_url rather than raised; the caller (backend/jobs/executors/
    audio.py) decides whether "some exercises still missing audio" should
    fail the job for a retry."""
    from ..hf_client import hf_client  # deferred import — this module's only use of hf_client

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
        audio_bytes, _media_type, filename = result
        problems = validate_audio_bytes(audio_bytes)
        if problems:
            logger.warning(
                "Audio synthesis for %s/%s exercise %s failed validation (%s) — publishing without audio_url",
                pair_key, unit_id, ex.id, "; ".join(problems),
            )
            continue
        ex.audio_url = f"/api/audio/{filename}"


def _pair_metadata_path(store, pair_key: str) -> str:
    return os.path.join(store.base_dir, _safe_component(pair_key), "pair_meta.json")


def _ensure_pair_metadata(store, pair_key: str, target_lang: str, native_lang: str) -> None:
    """Writes a small sidecar recording this pair_key's original
    target_lang/native_lang strings — language_pair_key's ":" separator
    doesn't survive _safe_component's filesystem-safe sanitization (it
    becomes "_", indistinguishable from a language name that genuinely
    contains an underscore), so backend/jobs/scanner.py's startup scan
    (which only sees sanitized directory names on disk, not the original
    call that created them) reads this back instead of trying to split
    the directory name and guess. Keyed off `store.base_dir` rather than
    settings.language_library_dir directly so tests (which construct
    their own FileSystemAcademyStore(tmp_path)) stay isolated."""
    path = _pair_metadata_path(store, pair_key)
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"target_lang": target_lang, "native_lang": native_lang}, f)


def read_pair_metadata(store, pair_key: str) -> tuple[str, str] | None:
    path = _pair_metadata_path(store, pair_key)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    return meta["target_lang"], meta["native_lang"]


def _needs_audio(raw_exercises: list[dict]) -> bool:
    return any(item.get("type") in _AUDIBLE_TYPE_VALUES and not item.get("audio_url") for item in raw_exercises)


def enqueue_audio_job(pair_key: str, level: str, unit_id: str, target_lang: str) -> None:
    """Queues (or, if a previous attempt for this exact unit exhausted its
    retries, re-queues — see JobManager.enqueue) the "audio_unit" job.
    Idempotent by design (dedupe_key): calling this for a unit that
    already has a pending/running/retrying/completed job for it is a
    no-op, so both a fresh build and a repair scan can call this
    unconditionally without needing to coordinate with each other."""
    job_manager.enqueue(
        job_type="audio_unit",
        payload={"pair_key": pair_key, "level": level, "unit_id": unit_id, "target_lang": target_lang},
        dedupe_key=f"audio_unit:{pair_key}:{level}:{unit_id}",
    )


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
    _ensure_pair_metadata(store, pair_key, target_lang, native_lang)
    report = BuildReport(language_pair=pair_key, level=level.value, version=version)
    units = curriculum.units_for_level(level)
    report.units_attempted = len(units)

    for unit in units:
        existing = store.load_course_asset(pair_key, level.value, unit.id, "content", version=version)
        if not force and existing:
            if _needs_audio(existing):
                enqueue_audio_job(pair_key, level.value, unit.id, target_lang)
            report.units_built += 1
            continue
        try:
            raw_exercises = await generators.generate_unit_exercises(unit, target_lang, native_lang)
        except GenerationError as exc:
            report.failures.append((unit.id, str(exc)))
            logger.error("Build failed for %s/%s unit %s: %s", pair_key, level.value, unit.id, exc)
            continue

        final_exercises = generators.wrap_with_teaching_intros(raw_exercises)
        final_dumped = [e.model_dump() for e in final_exercises]
        store.save_course_asset(pair_key, level.value, version, unit.id, "content", final_dumped)
        if _needs_audio(final_dumped):
            enqueue_audio_job(pair_key, level.value, unit.id, target_lang)
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
    """Scans the *currently published* version of this (pair, level) for
    units still missing audio_url and enqueues an "audio_unit" job for
    each (see enqueue_audio_job) — never calls a TTS provider itself.
    Existed originally (in an earlier revision of this function) as a
    synchronous, blocking migration path for content published before
    audio pre-generation existed at all; rewritten to go through the job
    queue for the same reason build_language_level does — a scan/backfill
    trigger should never itself be the thing waiting on a slow model
    download. Returns a BuildReport with a failure recorded for a level
    that isn't published at all (nothing to backfill onto)."""
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
        if _needs_audio(raw):
            enqueue_audio_job(pair_key, level.value, unit.id, target_lang)
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
            logger.info("Scanning %s:%s / %s for missing audio...", target_lang, native_lang, level.value)
            reports.append(await backfill_audio(store, target_lang, native_lang, level))
    return reports
