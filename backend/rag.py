"""Retrieval-augmented grounding for the academy: real reference material
pulled from public Open Educational Resources (OER), instead of relying only
on the chat model's training data, so curricula and courses cite something
real underneath the generated text.

Two sources for now — arXiv's public, keyless search API for STEM fields,
and Wikipedia's public, keyless REST API as a second source that covers
every field, including the humanities/arts/business/clinical fields arXiv
has no real content for — rather than the full OER stack (ESCO/O*NET, MIT
OCW, OpenStax, HF OER datasets, OpenLearn, PubMed Central, SciELO,
Kaggle/UCI) a proper version of this would eventually pull from. Two
reasons: (1) each of those sources needs its own licensing check and
ingestion/parsing work, which is a multi-week project, not a single pass;
(2) a "real" RAG stack (LangChain, a vector DB, a local sentence-
transformers embedding model) would add hundreds of MB of dependencies
(torch) to what is currently a lightweight `python:3.12-slim` deploy. Both
sources' own search endpoints already do relevance ranking, so this skips
building a separate embedding/vector-store step entirely — retrieval here
just means "ask the source's own search for the most relevant material."

Extending to another source later means adding another `fetch_*_context`
function following the same shape (query in, formatted grounding text out,
cached, never raises) and calling it from build_curriculum_prompt's caller.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import urllib.parse
from xml.etree import ElementTree as ET

import httpx

from .config import settings

logger = logging.getLogger("lingua.rag")

_ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Only fields with genuine arXiv coverage get grounding from it — humanities,
# arts, and licensure-heavy clinical fields don't have meaningful arXiv
# content, so they fall back to the model's own knowledge (unchanged from
# before this module existed).
ARXIV_CATEGORY_FOR_FIELD: dict[str, str] = {
    "computer-science": "cs.LG OR cs.AI OR cs.DS",
    "software-engineering": "cs.SE",
    "data-science": "cs.LG OR stat.ML",
    "artificial-intelligence": "cs.AI OR cs.LG",
    "cybersecurity": "cs.CR",
    "mathematics": "math.GM OR math.ST",
    "physics": "physics.gen-ph",
    "biology": "q-bio.PE OR q-bio.GN",
    "environmental-science": "physics.ao-ph",
    "economics": "econ.GN",
    "finance": "q-fin.GN",
    "civil-engineering": "physics.app-ph",
    "mechanical-engineering": "physics.app-ph",
    "electrical-engineering": "eess.SY",
    "psychology": "q-bio.NC",
}


def _cache_path(namespace: str, key: str) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"{namespace}-{digest}.txt")


async def fetch_arxiv_context(field_id: str, topic: str, max_results: int = 3) -> str:
    """Real arXiv abstracts relevant to (field, topic), formatted as grounding
    text for a generation prompt. Returns "" for fields with no arXiv
    coverage, on any network/parse failure, or when nothing relevant is
    found — this must never raise, since it only ever augments a prompt that
    works fine without it."""
    category = ARXIV_CATEGORY_FOR_FIELD.get(field_id)
    if not category:
        return ""

    cache_key = f"{field_id}:{topic}"
    cache_file = _cache_path("arxiv", cache_key)
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()
    if settings.testing:
        return ""

    query_terms = re.sub(r"[^\w\s]", " ", topic)
    search_query = f"cat:({category}) AND abs:({query_terms})"
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(_ARXIV_API, params=params)
        if resp.status_code != 200:
            return ""
        context = _format_arxiv_context(parse_arxiv_atom(resp.text))
        if not context:
            return ""
    except Exception:
        logger.exception("arXiv fetch failed for field=%s topic=%s", field_id, topic)
        return ""

    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(context)
    return context


def parse_arxiv_atom(xml_text: str) -> list[tuple[str, str]]:
    """Parses an arXiv Atom API response into (title, summary) pairs. Pure
    and network-free, so it's covered directly in tests without depending
    on arxiv.org's uptime."""
    root = ET.fromstring(xml_text)
    entries = root.findall("atom:entry", _ATOM_NS)
    results = []
    for entry in entries:
        title_el = entry.find("atom:title", _ATOM_NS)
        summary_el = entry.find("atom:summary", _ATOM_NS)
        if title_el is None or summary_el is None or not title_el.text or not summary_el.text:
            continue
        title = " ".join(title_el.text.split())
        summary = " ".join(summary_el.text.split())[:500]
        results.append((title, summary))
    return results


def _format_arxiv_context(papers: list[tuple[str, str]]) -> str:
    if not papers:
        return ""
    blurbs = [f"- {title}: {summary}" for title, summary in papers]
    return (
        "Real, current research abstracts from arXiv (for grounding — "
        "reference these ideas where relevant, don't just repeat them "
        "verbatim):\n" + "\n".join(blurbs)
    )


_WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/rest.php/v1/search/page"
_WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
# Wikimedia's API etiquette policy requires a descriptive User-Agent
# identifying the app and a contact point; requests with a generic/blank one
# (httpx's default is just "python-httpx/<version>") get a flat HTTP 403.
# https://meta.wikimedia.org/wiki/User-Agent_policy
_WIKIMEDIA_USER_AGENT = "Lingua-LanguageApp/1.0 (https://language-ai-x90j9w.fly.dev; academy content grounding)"


async def fetch_wikipedia_context(topic: str, max_results: int = 2) -> str:
    """Real Wikipedia article summaries relevant to `topic`, formatted as
    grounding text — the same role fetch_arxiv_context plays for STEM
    fields, but for everything else: humanities, arts, business, clinical
    fields, trades, anything with an encyclopedia article. Both of
    Wikipedia's REST endpoints used here (search, then per-title summary)
    are public and keyless. Returns "" on any network/parse failure or
    when nothing relevant is found — this must never raise, since it only
    ever augments a prompt that works fine without it."""
    cache_file = _cache_path("wikipedia", topic)
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()
    if settings.testing:
        return ""

    try:
        headers = {"User-Agent": _WIKIMEDIA_USER_AGENT}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            search_resp = await client.get(_WIKIPEDIA_SEARCH_API, params={"q": topic, "limit": max_results})
            if search_resp.status_code != 200:
                return ""
            pages = search_resp.json().get("pages", [])[:max_results]
            if not pages:
                return ""

            blurbs = []
            for page in pages:
                title = page.get("title")
                if not title:
                    continue
                summary_resp = await client.get(f"{_WIKIPEDIA_SUMMARY_API}/{urllib.parse.quote(title)}")
                if summary_resp.status_code != 200:
                    continue
                extract = " ".join(summary_resp.json().get("extract", "").split())[:500]
                if extract:
                    blurbs.append(f"- {title}: {extract}")
    except Exception:
        logger.exception("Wikipedia fetch failed for topic=%s", topic)
        return ""

    if not blurbs:
        return ""
    context = (
        "Real, reference material from Wikipedia (for grounding — reference "
        "these facts where relevant, don't just repeat them verbatim):\n" + "\n".join(blurbs)
    )
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(context)
    return context
