"""Startup/periodic scan for missing assets -> enqueue jobs to repair
them (the "Asset Repair Worker" — there's no separate repair code path;
repairing a gap and generating it for the first time are the same
operation to an idempotent executor like audio's, so the only thing a
"repair worker" needs is something to notice the gap and enqueue the
same job type. That's what this module is.).

Implemented today: audio (language_library units' vocab_intro/listen_type
exercises missing audio_url) — the concrete gap this whole redesign was
triggered by.

Deliberately NOT implemented yet, listed here so extending this is a
checklist rather than a redesign:
  - images (backend/routers/content.py's /image already generates these
    on demand rather than pre-generating anything, so there's no
    persisted "image_url" field yet to scan for the absence of)
  - embeddings (no embedding of any kind exists anywhere in this codebase
    today — nothing to be missing)
  - tutor biographies (backend/personas.py's TeacherPersona fields are
    all hand-authored constants, not generated content with a
    build/publish step)
  - prerequisite graph completeness (backend/learning_engine/
    knowledge_graph.py's course-level and concept-level edges are
    produced by scripts/build_academy.py at course-build time already;
    auditing an existing graph for gaps is a different, real feature
    this scan doesn't attempt)
  - curriculum completeness (academy_library's per-field/level
    curriculum+course content already 404s cleanly when unbuilt — see
    routers/academy.py — rather than silently serving a hole; scanning
    for *which* (field, level) pairs are unbuilt across the ~60-field
    catalog and auto-enqueueing their generation is a real, separate
    feature, not implemented here)
Each of the above becomes a `scan_missing_<type>()` function following
build_language_level's own shape (discover published content -> check
for the gap -> job_manager.enqueue), plus one executors/<type>.py and one
bootstrap.py registration — additive, not a rewrite of this module or
anything it calls.
"""

from __future__ import annotations

import logging
import os

from ..config import settings
from ..language_library import build as language_build
from ..language_library.storage import FileSystemAcademyStore
from ..models import CEFRLevel

logger = logging.getLogger("lingua.jobs.scanner")


def _discover_built_pairs() -> list[str]:
    """Every pair_key with at least one published level, discovered by
    walking language_library_dir's on-disk layout — the store itself has
    no enumeration method (academy_library/storage.py's AcademyStore
    Protocol is a plain per-field/level lookup, not a listing API), so
    this is necessarily filesystem-specific rather than something a
    non-filesystem store implementation would need to support the same
    way."""
    base = settings.language_library_dir
    if not os.path.isdir(base):
        return []
    return [name for name in os.listdir(base) if os.path.isdir(os.path.join(base, name))]


async def scan_missing_audio() -> int:
    """The audio Asset Repair scan: for every pair/level actually
    published, enqueues an "audio_unit" job for any unit still missing
    audio_url (build_language_level/backfill_audio already enqueue this
    at build time — this is the safety net that catches anything built
    before that existed, or any job that previously exhausted its
    retries and needs another try after whatever was wrong got fixed).
    Returns the number of (pair, level) combinations scanned."""
    store = FileSystemAcademyStore(settings.language_library_dir)
    scanned = 0
    for pair_key in _discover_built_pairs():
        meta = language_build.read_pair_metadata(store, pair_key)
        if meta is None:
            logger.warning("skipping %s: no pair_meta.json (built by a version of this app before it existed)", pair_key)
            continue
        target_lang, native_lang = meta
        for level in CEFRLevel:
            if store.get_latest_version(pair_key, level.value) is None:
                continue
            await language_build.backfill_audio(store, target_lang, native_lang, level)
            scanned += 1
    logger.info("audio scan complete: %d (pair, level) combination(s) checked", scanned)
    return scanned
