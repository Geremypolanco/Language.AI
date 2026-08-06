"""Proactive academy-library builder — the PRIMARY mechanism behind "no
page can ever say content unavailable" (see auto_build.py's module
docstring for the on-demand safety net this backs up, for the narrow
window before this loop catches up to a given field/level).

Runs as a lightweight periodic background task (see main.py's lifespan),
the same pattern as cache_gc.run_periodic_gc: one bounded unit of work per
tick, then sleep, for as long as the app is up. Walks every academic field
(base fields before their own specializations — a specialization's served
curriculum composes over its base field's already-built courses, see
routers/academy.py's _load_curriculum, so building bases first means a
specialization's first real read never needs the on-demand safety net
either) x every AcademicLevel, and for whichever one is still incomplete,
does ONE more bounded step of progress via the same resumable
build.build_field_level/build_course this whole library already uses — so
a process restart mid-catch-up just resumes where it left off, never
duplicates or corrupts anything (this is exactly why build_field_level was
already designed to be resumable, long before this loop existed).

Scale note: the full academy catalog (~60 fields x 3 levels, up to 24
courses each x 7 asset kinds, plus a prerequisite-graph pass and a tutor
biography per field) is thousands of AI calls — a first full pass realistically
takes hours, not minutes, running entirely in the background with zero
impact on any request being served in the meantime (every field/level this
loop hasn't reached yet is still covered by auto_build.py's on-demand
safety net, so a real user is never blocked on this loop's own pace).
Chat's primary path (Groq/Pollinations — see hf_client.py) is free and
carries no daily budget guard, so this doesn't meaningfully draw down the
one paid/budget-guarded tier (Hugging Face) unless both of those are down,
in which case chat() — and this loop's progress — simply stalls until they
recover, rather than burning through HF's budget.
"""

from __future__ import annotations

import asyncio
import logging

from .. import academy
from ..config import settings
from ..models import AcademicField, AcademicLevel
from . import auto_build, build
from .storage import AcademyStore, get_default_store

logger = logging.getLogger("lingua.academy_library.proactive_builder")


def _ordered_fields() -> list[AcademicField]:
    """Base fields (base_field_id is None) before their specializations —
    an ordering concern only (build.build_field_level itself doesn't care
    what order fields are built in); it just means a specialization is
    rarely, if ever, attempted before the base it composes over."""
    fields = academy.all_fields()
    return [f for f in fields if not f.base_field_id] + [f for f in fields if f.base_field_id]


async def _next_incomplete_unit(store: AcademyStore) -> tuple[AcademicField, AcademicLevel, dict | None] | None:
    """The next (field, level) that isn't fully built yet, in a stable
    order every tick restarts from. `curriculum` is None when nothing has
    been generated for it at all yet (needs the fast-path start); a
    non-None curriculum with an incomplete course set or missing biography
    means the field genuinely has more work pending. Cheap: pure disk
    reads (JSON existence checks), and the catalog is small (~60 fields x
    3 levels) — this only runs once per interval_s tick, never per
    request."""
    for field in _ordered_fields():
        for level in AcademicLevel:
            curriculum = store.load_curriculum(field.id, level.value)
            if curriculum is None:
                return field, level, None
            course_ids = [build.course_id_for(field.id, level, i) for i in range(len(curriculum["courses"]))]
            if not store.is_complete(field.id, level.value, course_ids):
                return field, level, curriculum
            if store.load_field_biography(field.id) is None:
                return field, level, curriculum
    return None


async def _populate_graph(field: AcademicField, level: AcademicLevel, course_ids: list[str], courses: list[dict], native_lang: str) -> None:
    """Sequential baseline (guaranteed, free, deterministic) plus the
    AI-driven non-adjacent-edge enrichment on top of it — both best-effort,
    never allowed to interrupt the build loop itself (see
    knowledge_graph.enrich_prerequisite_graph's own docstring for why it
    already never raises; build_graph_for_field_level is pure SQL and only
    fails on a genuine bug, which is still worth not crashing the loop
    over)."""
    from ..learning_engine import knowledge_graph

    try:
        knowledge_graph.build_graph_for_field_level(field.id, level.value, course_ids, store=get_default_store())
    except Exception:
        logger.exception("Sequential prerequisite chain failed for %s/%s", field.id, level.value)
        return
    try:
        await knowledge_graph.enrich_prerequisite_graph(field, level, course_ids, courses, native_lang)
    except Exception:
        logger.exception("Prerequisite-graph enrichment failed for %s/%s", field.id, level.value)


async def _build_one_step(store: AcademyStore, native_lang: str) -> bool:
    """Does ONE bounded unit of work and returns whether any was found —
    False means the whole catalog is fully built (curriculum + every
    course's assets + prerequisite graph + tutor biography, for every
    field and level)."""
    unit = await _next_incomplete_unit(store)
    if unit is None:
        return False
    field, level, curriculum = unit

    if curriculum is None:
        await auto_build.ensure_field_level_started(store, field, level, native_lang)
        return True

    course_ids = [build.course_id_for(field.id, level, i) for i in range(len(curriculum["courses"]))]
    if not store.is_complete(field.id, level.value, course_ids):
        version = store.get_latest_version(field.id, level.value)
        if version is None:
            return True  # curriculum saved but never flipped to latest (a previous run failed) — nothing safe to resume from here
        report = await build.build_field_level(store, field, level, native_lang, version)
        if report.ok:
            await _populate_graph(field, level, course_ids, curriculum["courses"], native_lang)
        return True

    if store.load_field_biography(field.id) is None:
        await build.build_field_biography(store, field, native_lang)
        return True

    return True  # defensive: _next_incomplete_unit wouldn't have returned this unit otherwise


async def run_periodic_academy_build(interval_s: float | None = None) -> None:
    """Builds the whole academy library, one bounded step at a time, for
    as long as the app is up — started as a background task from main.py's
    lifespan, the same pattern as cache_gc.run_periodic_gc. Every iteration
    is wrapped in its own try/except so one bad step never kills the loop
    or the app."""
    interval = settings.academy_build_interval_s if interval_s is None else interval_s
    store = get_default_store()
    while True:
        try:
            await _build_one_step(store, settings.academy_build_native_lang)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Proactive academy build step failed")
        await asyncio.sleep(interval)
