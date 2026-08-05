"""Embedding Router — real Hugging-Face-hosted sentence embeddings
(BAAI/bge-m3, see registry.py's AITask.EMBEDDING) powering semantic search
and similarity ranking:

    Embeddings -> Embedding Router -> ideal model

A genuinely new capability this app didn't have before this orchestrator —
previously "recommendations" meant asking the chat model to name titles
from memory (see hf_client.generate_recommendations), never real vector
search over the app's own catalog. See routers/library.py's semantic
search endpoint for where this is actually used."""

from __future__ import annotations

import math

from ...hf_client import hf_client
from ..registry import AITask, chain_for


class EmbeddingRouter:
    @property
    def active_chain(self):
        return chain_for(AITask.EMBEDDING)

    async def embed(self, text: str) -> list[float] | None:
        return await hf_client.embed_text(text)

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def semantic_rank(self, query: str, candidates: list[str], top_k: int = 5) -> list[tuple[int, float]]:
        """Ranks `candidates` by semantic similarity to `query`, best-first,
        as (original_index, score) pairs. Returns [] — never raises — when
        embeddings are unavailable (no HF token configured, the daily
        budget exhausted, a rate limit, or running in tests), so callers can
        fall back to plain keyword filtering instead of breaking search
        entirely, the same graceful-degrade shape as every other AI feature
        in this app.

        Deliberately sequential (one HF call per candidate, no batch
        endpoint to lean on): each embedding is disk-cached forever (see
        hf_client.embed_text), so a repeated search over the same or
        overlapping candidates only ever pays the network cost once.
        Callers are responsible for bounding `candidates` to a reasonable
        size per request — see registry.py's AITask.EMBEDDING follow-up
        note about a precomputed full-catalog index for unbounded search."""
        query_vec = await self.embed(query)
        if query_vec is None:
            return []
        scored: list[tuple[int, float]] = []
        for i, text in enumerate(candidates):
            vec = await self.embed(text)
            if vec is None:
                continue
            scored.append((i, self.cosine_similarity(query_vec, vec)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
