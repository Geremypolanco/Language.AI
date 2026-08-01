"""YouTube search utility for educational videos.
Uses a best-effort approach to find relevant video IDs based on a query.

Scraping YouTube's search-results HTML (rather than the official Data API,
which needs a quota'd API key) is inherently fragile — Google can change the
page's embedded JSON shape at any time — and repeating it on every request
is the kind of hammering that gets an IP rate-limited or flagged. Results
are therefore cached to disk (same content-hash pattern as image_search.py)
for a week, which both cuts request volume drastically and, if a stale cache
exists, gives a "graceful fallback": a scrape that returns nothing (page
structure changed, transient block, network hiccup) still serves the last
known-good results instead of leaving the caller with an empty list.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from urllib.parse import quote

import httpx

from .config import settings

logger = logging.getLogger("lingua.youtube_search")

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
_http = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT})
_CACHE_TTL_SECONDS = 7 * 24 * 3600


def _cache_path(query: str, limit: int) -> str:
    digest = hashlib.sha256(f"{query}:{limit}".encode()).hexdigest()[:32]
    return os.path.join(settings.cache_dir, f"ytsearch-{digest}.json")


def _read_cache(cache_path: str) -> list[dict[str, str]] | None:
    try:
        with open(cache_path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


async def search_youtube_videos(query: str, limit: int = 1) -> list[dict[str, str]]:
    """
    Searches YouTube for videos matching the query and returns a list of video data.
    Returns: [{'id': 'video_id', 'title': 'video_title', 'thumbnail': 'url'}]
    """
    cache_path = _cache_path(query, limit)
    if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < _CACHE_TTL_SECONDS:
        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

    try:
        # Search URL
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        resp = await _http.get(url)
        if resp.status_code != 200:
            logger.warning("YouTube search failed with status %s", resp.status_code)
            return _read_cache(cache_path) or []

        # Simple regex to find video IDs in the page source
        # Looking for "videoRenderer":{"videoId":"..."
        video_ids = re.findall(r'"videoRenderer":{"videoId":"([^"]+)"', resp.text)

        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for vid in video_ids:
            if vid not in seen:
                unique_ids.append(vid)
                seen.add(vid)
            if len(unique_ids) >= limit:
                break

        results = []
        for vid in unique_ids:
            results.append({
                "id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "embed_url": f"https://www.youtube.com/embed/{vid}",
                "thumbnail": f"https://img.youtube.com/vi/{vid}/0.jpg"
            })

        if not results:
            # Page structure likely changed underneath the regex — fall back
            # to a stale cache (even past TTL) rather than an empty result.
            return _read_cache(cache_path) or []

        os.makedirs(settings.cache_dir, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(results, f)
        return results
    except Exception:
        logger.exception("YouTube search failed")
        return _read_cache(cache_path) or []
