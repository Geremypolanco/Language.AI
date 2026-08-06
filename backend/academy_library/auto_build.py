"""On-demand build safety net — NOT the primary mechanism for "the academy
is always ready" (see proactive_builder.py for that: a background task that
builds the whole library ahead of time, so a real student essentially never
hits this module in practice). This exists for the narrow window where a
student reaches a (field, level) before the proactive builder gets to it —
right after a fresh deploy, or right after a new field is added to
backend/academy.py's catalog — so "aún no está disponible" never has a path
to actually reach the UI, even during that catch-up window.

Two shapes, mirroring build.py's own split:

- ensure_field_level_started(): bounded, synchronous — builds just the
  curriculum shell + first course (build_field_level(..., max_courses=1)),
  so a caller waiting on this gets a real, servable answer in roughly one
  course's worth of generation time, never a whole field's.
- ensure_course_built(): bounded, synchronous — builds whatever's still
  missing for ONE course whose field/level curriculum already exists.
- ensure_background_completion(): fire-and-forget — schedules the REST of
  a (field, level) to finish building via the same resumable
  build_field_level(), deduplicated per-process so concurrent requests for
  the same unfinished field/level don't each spawn a redundant completion
  job.

Every function here is best-effort: none of them raise. A failure just
means the caller falls through to whatever it already did before this
module existed (the legacy unpersisted on-demand generator, or a 404) —
this module can only ever make "not available" less likely, never worse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from . import build
from .storage import AcademyStore

if TYPE_CHECKING:
    from ..models import AcademicField, AcademicLevel, CEFRLevel

logger = logging.getLogger("lingua.academy_library.auto_build")

# (field_id, level) pairs with a background completion task currently
# in flight in THIS process — process-local, not persisted (see
# proactive_builder.py's module docstring for why that's an accepted
# tradeoff for a single-worker deployment: a restart just means the next
# request re-triggers completion, which is safe since build_field_level is
# resumable and skips everything already saved).
_completion_in_flight: set[tuple[str, str]] = set()


async def ensure_field_level_started(
    store: AcademyStore,
    field: "AcademicField",
    level: "AcademicLevel",
    content_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> str | None:
    """If field/level has never been built, synchronously builds the
    curriculum shell + course 0 and flips `latest` the moment that
    succeeds — bounded to roughly one course's generation time, never a
    whole field's. A no-op with zero AI calls if a curriculum is already
    persisted (whether fully or partially built), so this is safe to call
    on every request. Returns the resulting latest version string, or None
    if nothing is built and this call didn't manage to build it either."""
    already = store.load_curriculum(field.id, level.value)
    if already is not None:
        return store.get_latest_version(field.id, level.value)

    try:
        version = build.next_version(store, field.id, level.value)
        report = await build.build_field_level(
            store, field, level, content_lang, version, max_courses=1, cefr_level=cefr_level
        )
    except Exception:
        logger.exception("Auto-build fast path raised for %s/%s", field.id, level.value)
        return None
    if not report.ok:
        return None  # build_field_level already logged the specific failures

    try:
        await build.build_field_biography(store, field, content_lang)
    except Exception:
        logger.exception("Auto-build tutor biography failed for %s", field.id)

    return store.get_latest_version(field.id, level.value)


async def ensure_course_built(
    store: AcademyStore,
    field: "AcademicField",
    level: "AcademicLevel",
    course_id: str,
    title: str,
    description: str,
    content_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> list[tuple[str, str]]:
    """Builds whatever asset kinds are still missing for ONE course, when
    the field/level's curriculum is already persisted but the proactive
    builder hasn't reached this specific course yet. Requires a persisted
    curriculum — if the field/level was never built at all, there is no
    version to build against, so this returns immediately without
    attempting anything (the caller's existing legacy/404 path applies)."""
    version = store.get_latest_version(field.id, level.value)
    if version is None:
        return [("curriculum", "no persisted curriculum for this field/level")]
    try:
        return await build.build_course(
            store, field, level, version, course_id, title, description, content_lang, cefr_level=cefr_level
        )
    except Exception:
        logger.exception("Auto-build safety net failed for course %s", course_id)
        return [("unknown", "unexpected error during on-demand build")]


def ensure_background_completion(
    store: AcademyStore,
    field: "AcademicField",
    level: "AcademicLevel",
    content_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> None:
    """Fire-and-forget: schedules the rest of a (field, level) to finish
    building in the background, unless it's already complete or already
    has a completion task running. Must be called from within a running
    event loop (every call site here is an async request handler or the
    async proactive-builder loop)."""
    key = (field.id, level.value)
    if key in _completion_in_flight:
        return

    curriculum = store.load_curriculum(field.id, level.value)
    if curriculum is not None:
        course_ids = [build.course_id_for(field.id, level, i) for i in range(len(curriculum["courses"]))]
        if store.is_complete(field.id, level.value, course_ids):
            return

    _completion_in_flight.add(key)

    async def _finish() -> None:
        try:
            version = store.get_latest_version(field.id, level.value) or build.next_version(store, field.id, level.value)
            await build.build_field_level(store, field, level, content_lang, version, cefr_level=cefr_level)
            await build.build_field_biography(store, field, content_lang)
        except Exception:
            logger.exception("Background completion failed for %s/%s", field.id, level.value)
        finally:
            _completion_in_flight.discard(key)

    asyncio.create_task(_finish())
