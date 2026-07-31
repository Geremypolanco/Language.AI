"""Query-time retrieval: turns a course/topic request into grounded OER
excerpts + citations for backend/academy.py to fold into its generation
prompt (see build_course_prompt's `grounding` parameter)."""

from __future__ import annotations

from dataclasses import dataclass

from . import vectorstore
from .embeddings import embed_texts


@dataclass
class RetrievedChunk:
    text: str
    title: str
    source: str
    url: str


async def retrieve_context(query: str, field_id: str | None = None, k: int = 4) -> list[RetrievedChunk]:
    """Embeds `query` and returns up to `k` grounding chunks, preferring ones
    tagged with `field_id`. Falls back to the whole store when nothing is
    tagged for that field yet, rather than returning no grounding at all —
    the vector store is populated incrementally (see scripts/ingest_oer.py),
    so most fields won't have dedicated content on day one."""
    embeddings = await embed_texts([query])
    if not embeddings:
        return []
    embedding = embeddings[0]

    where = {"field_id": field_id} if field_id else None
    hits = vectorstore.query(embedding, k=k, where=where)
    if not hits and where:
        hits = vectorstore.query(embedding, k=k)

    return [
        RetrievedChunk(
            text=h["text"],
            title=h["metadata"].get("title", ""),
            source=h["metadata"].get("source", ""),
            url=h["metadata"].get("url", ""),
        )
        for h in hits
    ]
