"""Executor + validator for the "audio_unit" job type: synthesizes and
persists audio for every vocab_intro/listen_type exercise in one
already-persisted unit that's still missing audio_url.

Reuses language_library.build's _attach_audio for the actual per-exercise
work — the only thing that changed by moving this behind a job is *where*
that call happens (inside a worker-claimed job, immune to whatever
script/session/SSH-tunnel enqueued the job) rather than *what* it does.
"""

from __future__ import annotations

from typing import Any

from ...language_library import build as language_build
from ...language_library.storage import FileSystemAcademyStore
from ...models import Exercise


async def execute(payload: dict[str, Any]) -> dict[str, Any]:
    pair_key = payload["pair_key"]
    level = payload["level"]
    unit_id = payload["unit_id"]
    target_lang = payload["target_lang"]

    from ...config import settings

    store = FileSystemAcademyStore(settings.language_library_dir)
    version = store.get_latest_version(pair_key, level)
    if version is None:
        raise RuntimeError(f"{pair_key}/{level} has no published version (unpublished after this job was queued?)")
    raw = store.load_course_asset(pair_key, level, unit_id, "content", version=version)
    if raw is None:
        raise RuntimeError(f"{pair_key}/{level}/{unit_id} content is missing (removed after this job was queued?)")

    exercises = [Exercise(**item) for item in raw]
    before = [e.audio_url for e in exercises]
    await language_build._attach_audio(exercises, target_lang, pair_key, unit_id)
    after = [e.audio_url for e in exercises]

    if after != before:
        # Persist whatever progress was made even if the unit ends up
        # still incomplete below — a retry (see manager.fail's backoff)
        # only ever has to redo the exercises still missing audio_url,
        # never the ones this attempt already finished.
        store.save_course_asset(pair_key, level, version, unit_id, "content", [e.model_dump() for e in exercises])

    still_missing = [e.id for e in exercises if e.type in language_build._AUDIBLE_TYPES and not e.audio_url]
    newly_set = sum(1 for a, b in zip(after, before, strict=True) if a and a != b)
    if still_missing:
        raise RuntimeError(
            f"{len(still_missing)} exercise(s) still missing audio after this attempt "
            f"(set {newly_set} more this run): {still_missing}"
        )
    return {"pair_key": pair_key, "level": level, "unit_id": unit_id, "audio_urls_set": newly_set}


def validate(result: Any) -> list[str]:
    if not isinstance(result, dict) or "unit_id" not in result:
        return ["executor returned an unexpected result shape"]
    return []
