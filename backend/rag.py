"""Retrieval-augmented grounding for the academy: real reference material
pulled from public Open Educational Resources (OER), instead of relying only
on the chat model's training data, so curricula and courses cite something
real underneath the generated text.

This is deliberately scoped to ONE source for now — arXiv's public, keyless
search API — rather than the full OER stack (ESCO/O*NET, MIT OCW, OpenStax,
HF OER datasets, OpenLearn, PubMed Central, SciELO, Kaggle/UCI) a proper
version of this would eventually pull from. Two reasons: (1) each of those
sources needs its own licensing check and ingestion/parsing work, which is a
multi-week project, not a single pass; (2) a "real" RAG stack (LangChain,
a vector DB, a local sentence-transformers embedding model) would add
hundreds of MB of dependencies (torch) to what is currently a lightweight
`python:3.12-slim` deploy. arXiv's own search endpoint already does semantic
relevance ranking, so this skips building a separate embedding/vector-store
step entirely for this first source — retrieval here just means "ask arXiv's
own search for the most relevant abstracts."

Extending to another source later means adding another `fetch_*_context`
function following the same shape (query in, formatted grounding text out,
cached, never raises) and calling it from build_curriculum_prompt's caller.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
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


def _cache_path(key: str) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"arxiv-{digest}.txt")


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
    cache_file = _cache_path(cache_key)
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()

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
