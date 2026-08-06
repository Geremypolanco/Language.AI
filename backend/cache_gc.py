"""Keeps the on-disk media/content cache (backend/config.py's cache_dir)
under a size budget via simple LRU eviction — a free, code-only way to stop
the Fly volume from filling up as generated images/video/book text/RAG
context accumulate, instead of paying to grow the volume. Runs as a
lightweight periodic background task (see main.py's lifespan), not on every
cache write, so it never adds latency to a request.

Synthesized speech and downloaded Piper voice models live under the
separate, never-evicted audio_store_dir instead (see backend/hf_client.py's
text_to_speech and backend/piper_tts.py) — audio is expensive enough to
regenerate on the spot (a cold voice download, a cold Parler-TTS Space,
an HF round trip) that silently evicting it to make room for a vocabulary
image would just reintroduce the exact latency spikes that break a
click-triggered play() (see routers/audio.py), for content this app
already promises is pre-generated once and reused forever.
"""

from __future__ import annotations

import asyncio
import logging
import os

from .config import settings

logger = logging.getLogger("lingua.cache_gc")


def _iter_cache_files(cache_dir: str) -> list[tuple[str, os.stat_result]]:
    entries = []
    for root, _dirs, files in os.walk(cache_dir):
        for name in files:
            path = os.path.join(root, name)
            try:
                entries.append((path, os.stat(path)))
            except FileNotFoundError:
                continue  # removed mid-walk by a concurrent request — fine, skip it
    return entries


def enforce_cache_budget(max_bytes: int, cache_dir: str | None = None) -> int:
    """Deletes least-recently-accessed cache files under cache_dir (default:
    settings.cache_dir) until total size is back under max_bytes. Safe to
    call anytime: every file under cache_dir is a pure optimization —
    regenerable content (exercises, images, audio, arXiv/Wikipedia
    grounding text) or a re-downloadable Piper voice model — never the only
    copy of anything, so eviction never loses real data, just a future
    cache hit. Returns bytes freed. Takes cache_dir explicitly (rather than
    always reading settings.cache_dir) so tests can point it at a temp
    directory without mutating the frozen global Settings singleton."""
    entries = _iter_cache_files(cache_dir if cache_dir is not None else settings.cache_dir)
    total = sum(st.st_size for _path, st in entries)
    if total <= max_bytes:
        return 0

    entries.sort(key=lambda e: e[1].st_atime)  # oldest-accessed first
    freed = 0
    removed = 0
    for path, st in entries:
        if total - freed <= max_bytes:
            break
        try:
            os.remove(path)
            freed += st.st_size
            removed += 1
        except FileNotFoundError:
            continue

    if removed:
        logger.info(
            "Cache GC: removed %d file(s), freed %.1f MB (budget %.1f MB, was %.1f MB)",
            removed,
            freed / 1e6,
            max_bytes / 1e6,
            total / 1e6,
        )
    return freed


async def run_periodic_gc(interval_s: float = 1800.0) -> None:
    """Runs enforce_cache_budget() on a fixed interval for as long as the
    app is up — started as a background task from main.py's lifespan.
    Every iteration is wrapped in its own try/except so one bad run (e.g. a
    transient disk error) never kills the loop or the app."""
    while True:
        try:
            await asyncio.to_thread(enforce_cache_budget, settings.cache_max_bytes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Cache GC pass failed")
        await asyncio.sleep(interval_s)
