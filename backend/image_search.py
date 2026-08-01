"""Free image search for vocabulary flashcards — a simpler, cheaper
alternative to the FLUX.1-schnell/Pollinations AI generation in
hf_client.py. Two real-photo sources, tried in order, both optional-vs-
always-on in a specific way:

1. Google's Custom Search JSON API (image search) — free up to 100
   queries/day, but needs one-time setup:
     a. https://programmablesearchengine.google.com/ — create a search
        engine, turn on "Search the entire web" and "Image search", copy
        its Search engine ID (cx).
     b. https://console.cloud.google.com/apis/credentials — create an API
        key with the "Custom Search API" enabled.
     c. Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX.
   With neither set, search_image() always returns None immediately.

2. Wikimedia Commons' own public search API — needs no key, no setup, no
   quota at all, so it's a genuinely free-out-of-the-box fallback for
   installs that never configure Google CSE. Lower average relevance than
   Google's general image search (it only searches Commons' own media
   library, an encyclopedia's illustration set — great for concrete nouns
   like "apple" or "hospital", weaker for very abstract vocabulary), which
   is exactly why it's second, not first.

Both fall through to AI generation (hf_client.generate_image) when they
return nothing — see routers/content.py's /image endpoint for the order.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os

import httpx

from .config import settings

logger = logging.getLogger("lingua.image_search")

_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_COMMONS_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
# Wikimedia's API etiquette policy requires a descriptive User-Agent
# identifying the app and a contact point; a generic/blank one (httpx's
# default is just "python-httpx/<version>") gets a flat HTTP 403.
# https://meta.wikimedia.org/wiki/User-Agent_policy
_WIKIMEDIA_USER_AGENT = "Lingua-LanguageApp/1.0 (https://language-ai-x90j9w.fly.dev; vocab flashcard images)"
_http = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
_commons_http = httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={"User-Agent": _WIKIMEDIA_USER_AGENT})


def _cache_path(namespace: str, query: str) -> str:
    digest = hashlib.sha256(query.encode()).hexdigest()[:32]
    return os.path.join(settings.cache_dir, f"{namespace}-{digest}.jpg")


async def _get_with_retry(url: str, *, client: httpx.AsyncClient = _http, **kwargs) -> httpx.Response:
    """One retry on a transient network failure — the same DNS-blip
    (httpx.ConnectError: "No address associated with hostname") seen on
    hf_client's calls has hit any outbound host on this machine, not just
    huggingface.co, so this source gets the same one-retry treatment."""
    for attempt in range(2):
        try:
            return await client.get(url, **kwargs)
        except httpx.TransportError:
            if attempt == 1:
                raise
            await asyncio.sleep(0.5)
    raise AssertionError("unreachable")


async def search_image(query: str) -> bytes | None:
    """Returns the bytes of the first safe-search Google image result for
    `query`, cached to disk thereafter (same pattern as hf_client's media
    caches). Never raises — any failure just means "no image from this
    source"."""
    if not settings.google_images_configured:
        return None

    cache_path = _cache_path("gimg", query)
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()

    try:
        resp = await _get_with_retry(
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

        image_resp = await _get_with_retry(items[0]["link"])
        if image_resp.status_code != 200 or not image_resp.headers.get("content-type", "").startswith("image"):
            return None

        with open(cache_path, "wb") as f:
            f.write(image_resp.content)
        return image_resp.content
    except Exception:
        logger.exception("Google image search failed")
        return None


async def search_images(query: str, count: int = 4) -> list[bytes]:
    """Like search_image(), but returns up to `count` distinct results for
    a real image gallery (see routers/content.py's /image-gallery-item) —
    one real search call per source, each result cached individually by
    (query, index) so repeat requests for the same gallery are free.
    Google CSE first, Wikimedia Commons fallback if Google isn't
    configured or returns nothing; never raises."""
    results = await _search_images_google(query, count)
    if results:
        return results
    return await _search_images_wikimedia(query, count)


async def _search_images_google(query: str, count: int) -> list[bytes]:
    if not settings.google_images_configured:
        return []

    cached = [p for i in range(count) if os.path.exists(p := _cache_path(f"gimg-gallery-{i}", query))]
    if len(cached) == count:
        return [open(p, "rb").read() for p in cached]

    try:
        resp = await _get_with_retry(
            _SEARCH_ENDPOINT,
            params={
                "key": settings.google_cse_api_key,
                "cx": settings.google_cse_cx,
                "q": query,
                "searchType": "image",
                "num": min(count, 10),
                "safe": "active",
                "imgSize": "medium",
            },
        )
        if resp.status_code != 200:
            logger.warning("Google image search HTTP %s: %s", resp.status_code, resp.text[:200])
            return []
        items = resp.json().get("items") or []
        results = []
        for i, item in enumerate(items[:count]):
            try:
                image_resp = await _get_with_retry(item["link"])
                if image_resp.status_code != 200 or not image_resp.headers.get("content-type", "").startswith("image"):
                    continue
                cache_path = _cache_path(f"gimg-gallery-{i}", query)
                with open(cache_path, "wb") as f:
                    f.write(image_resp.content)
                results.append(image_resp.content)
            except Exception:
                continue
        return results
    except Exception:
        logger.exception("Google image gallery search failed")
        return []


async def _search_images_wikimedia(query: str, count: int) -> list[bytes]:
    cached = [p for i in range(count) if os.path.exists(p := _cache_path(f"wmimg-gallery-{i}", query))]
    if len(cached) == count:
        return [open(p, "rb").read() for p in cached]
    if settings.testing:
        return []

    try:
        resp = await _get_with_retry(
            _COMMONS_ENDPOINT,
            client=_commons_http,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6,
                "gsrlimit": count,
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": 800,
                "format": "json",
            },
        )
        if resp.status_code != 200:
            logger.warning("Wikimedia Commons gallery search HTTP %s: %s", resp.status_code, resp.text[:200])
            return []
        pages = (resp.json().get("query") or {}).get("pages") or {}
        infos = [p["imageinfo"][0] for p in pages.values() if p.get("imageinfo")]
        results = []
        for i, info in enumerate(infos[:count]):
            try:
                image_url = info.get("thumburl") or info.get("url")
                if not image_url or not str(info.get("mime", "")).startswith("image"):
                    continue
                image_resp = await _get_with_retry(image_url, client=_commons_http)
                if image_resp.status_code != 200 or not image_resp.headers.get("content-type", "").startswith("image"):
                    continue
                cache_path = _cache_path(f"wmimg-gallery-{i}", query)
                with open(cache_path, "wb") as f:
                    f.write(image_resp.content)
                results.append(image_resp.content)
            except Exception:
                continue
        return results
    except Exception:
        logger.exception("Wikimedia Commons gallery search failed")
        return []


async def search_wikimedia_commons(query: str) -> bytes | None:
    """Returns the bytes of a matching image from Wikimedia Commons'
    own media library, cached to disk thereafter. Needs no API key and has
    no quota, so unlike search_image() above this always runs — the
    fallback that's actually free out of the box, no setup required. Never
    raises — any failure just means "no image from this source"."""
    cache_path = _cache_path("wmimg", query)
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()
    if settings.testing:
        return None

    try:
        resp = await _get_with_retry(
            _COMMONS_ENDPOINT,
            client=_commons_http,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6,  # the File: namespace
                "gsrlimit": 1,
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": 800,
                "format": "json",
            },
        )
        if resp.status_code != 200:
            logger.warning("Wikimedia Commons search HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        pages = (resp.json().get("query") or {}).get("pages") or {}
        infos = [p["imageinfo"][0] for p in pages.values() if p.get("imageinfo")]
        if not infos:
            return None
        info = infos[0]
        image_url = info.get("thumburl") or info.get("url")
        if not image_url or not str(info.get("mime", "")).startswith("image"):
            return None

        image_resp = await _get_with_retry(image_url, client=_commons_http)
        if image_resp.status_code != 200 or not image_resp.headers.get("content-type", "").startswith("image"):
            return None

        with open(cache_path, "wb") as f:
            f.write(image_resp.content)
        return image_resp.content
    except Exception:
        logger.exception("Wikimedia Commons image search failed")
        return None
