"""Query-time retrieval: turns a course/topic request into grounded OER
excerpts + citations for backend/academy.py to fold into its generation
prompt (see build_course_prompt's `grounding` parameter).

Field isolation is strict, by design: a query scoped to one academic field
never falls back to chunks tagged for a different one. An accelerated
doctoral track spanning many disciplines must never let, say, Clinical
Psychology material bleed into a Political Science session just because the
Political Science namespace hasn't been ingested yet — an empty, honest
"nothing grounded" result is always correct where a cross-field guess would
not be, however well-intentioned the guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import vectorstore
from .embeddings import embed_texts

# chromadb's cosine space reports *distance* (1 - cosine_similarity), so a
# hit's similarity is 1 - distance. 0.82 is the caller-specified confidence
# floor — with real sentence-transformer embeddings this is a reasonable
# starting point for "actually on topic" (calibrate against real ingested
# data before relying on it in production; the demo-mode/test pseudo-
# embeddings in hf_client._offline_embedding are not semantically meaningful,
# so this threshold isn't calibratable against them).
DEFAULT_MIN_SIMILARITY = 0.82


@dataclass
class RetrievedChunk:
    text: str
    title: str
    source: str
    url: str
    similarity: float


async def retrieve_context(
    query: str,
    field_id: str | None = None,
    k: int = 4,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[RetrievedChunk]:
    """Embeds `query` and returns up to `k` grounding chunks tagged with
    `field_id`, each above `min_similarity`. Returns an empty list — never
    chunks from another field — when nothing in this field's namespace
    clears the confidence bar; callers (see academy.build_course_prompt)
    must treat that as "no verified source for this topic," not silently
    fall back to broader, unrelated material."""
    embeddings = await embed_texts([query])
    if not embeddings:
        return []
    embedding = embeddings[0]

    where = {"field_id": field_id} if field_id else None
    hits = vectorstore.query(embedding, k=k, where=where)

    chunks = []
    for h in hits:
        distance = h.get("distance")
        similarity = 1.0 - distance if distance is not None else 0.0
        if similarity < min_similarity:
            continue
        chunks.append(
            RetrievedChunk(
                text=h["text"],
                title=h["metadata"].get("title", ""),
                source=h["metadata"].get("source", ""),
                url=h["metadata"].get("url", ""),
                similarity=similarity,
            )
        )
    return chunks
