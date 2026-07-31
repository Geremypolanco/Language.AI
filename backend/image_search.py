"""Free image search for vocabulary flashcards — a simpler, cheaper
alternative to the FLUX.1-schnell AI generation in hf_client.py. Uses
Google's Custom Search JSON API (image search), which is free up to 100
queries/day. Requires one-time setup:

1. https://programmablesearchengine.google.com/ — create a search engine,
   turn on "Search the entire web" and "Image search", copy its Search
   engine ID (cx).
2. https://console.cloud.google.com/apis/credentials — create an API key
   with the "Custom Search API" enabled.
3. Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX.

Entirely optional: with neither set, search_image() always returns None and
callers fall back to AI generation, exactly as before this existed.
"""

from __future__ import annotations

import hashlib
import logging
import os

import httpx

from .config import settings

logger = logging.getLogger("lingua.image_search")

_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_http = httpx.AsyncClient(timeout=15.0, follow_redirects=True)


def _cache_path(query: str) -> str:
    digest = hashlib.sha256(query.encode()).hexdigest()[:32]
    return os.path.join(settings.cache_dir, f"gimg-{digest}.jpg")


async def search_image(query: str) -> bytes | None:
    """Returns the bytes of the first safe-search image result for `query`,
    cached to disk thereafter (same pattern as hf_client's media caches).
    Never raises — any failure just means "no image from this source"."""
    if not settings.google_images_configured:
        return None

    cache_path = _cache_path(query)
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()

    try:
        resp = await _http.get(
            _SEARCH_ENDPOINT,
            params={
                "key": settings.google_cse_api_key,
                "cx": settings.google_cse_cx,
                "q": query,
                "searchType": "image",
                "num": 1,
                "safe": "active",
                "imgSize": "medium",
            },
        )
        if resp.status_code != 200:
            logger.warning("Google image search HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        items = resp.json().get("items") or []
        if not items:
            return None

        image_resp = await _http.get(items[0]["link"])
        if image_resp.status_code != 200 or not image_resp.headers.get("content-type", "").startswith("image"):
            return None

        with open(cache_path, "wb") as f:
            f.write(image_resp.content)
        return image_resp.content
    except Exception:
        logger.exception("Google image search failed")
        return None
