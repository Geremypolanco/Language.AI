"""YouTube search utility for educational videos.
Uses a best-effort approach to find relevant video IDs based on a query.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

import httpx

logger = logging.getLogger("lingua.youtube_search")

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
_http = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT})

async def search_youtube_videos(query: str, limit: int = 1) -> list[dict[str, str]]:
    """
    Searches YouTube for videos matching the query and returns a list of video data.
    Returns: [{'id': 'video_id', 'title': 'video_title', 'thumbnail': 'url'}]
    """
    try:
        # Search URL
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        resp = await _http.get(url)
        if resp.status_code != 200:
            logger.warning("YouTube search failed with status %s", resp.status_code)
            return []

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
            
        return results
    except Exception:
        logger.exception("YouTube search failed")
        return []
