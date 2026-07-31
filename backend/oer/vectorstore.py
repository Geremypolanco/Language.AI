"""Persisted vector store for OER chunks, backed by ChromaDB.

Embeddings are always supplied explicitly by callers (see embeddings.py) —
the collection never falls back to Chroma's bundled default embedding
function, so this stays a light dependency (no onnxruntime/torch pulled in
transitively just to store vectors we already computed).
"""

from __future__ import annotations

from dataclasses import dataclass

import chromadb

from ..config import settings

_COLLECTION_NAME = "oer_chunks"

_client: chromadb.ClientAPI | None = None
_collection = None


@dataclass
class StoredChunk:
    id: str
    text: str
    metadata: dict


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.oer_chroma_dir)
        _collection = _client.get_or_create_collection(_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    return _collection


def upsert(chunks: list[StoredChunk], embeddings: list[list[float]]) -> None:
    if not chunks:
        return
    _get_collection().upsert(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[c.metadata for c in chunks],
    )


def query(embedding: list[float], k: int, where: dict | None = None) -> list[dict]:
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []
    result = collection.query(query_embeddings=[embedding], n_results=min(k, total), where=where or None)
    ids = result["ids"][0]
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = (result.get("distances") or [[None] * len(ids)])[0]
    return [
        {"id": ids[i], "text": docs[i], "metadata": metas[i], "distance": dists[i]}
        for i in range(len(ids))
    ]


def count() -> int:
    return _get_collection().count()


def reset_for_tests(path: str) -> None:
    """Points the module-level Chroma client at an isolated directory —
    mirrors backend/db.py's reset_for_tests so OER tests never touch the
    real persisted vector store."""
    global _client, _collection
    _client = chromadb.PersistentClient(path=path)
    _collection = _client.get_or_create_collection(_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
