"""Orchestrates fetch -> chunk -> embed -> upsert for OER documents.

This is what scripts/ingest_oer.py calls per source; nothing here runs on
a user request path — populating the vector store is a deliberately
separate, offline admin step.
"""

from __future__ import annotations

import logging

from . import chunking, vectorstore
from .embeddings import embed_texts
from .sources import OERDocument

logger = logging.getLogger("lingua.oer.ingest")

_BATCH_SIZE = 32


async def ingest_documents(docs: list[OERDocument], max_chars: int = 900, overlap: int = 120) -> int:
    """Chunks and embeds `docs`, upserting the resulting chunks into the
    vector store. Returns the number of chunks written."""
    chunks: list[vectorstore.StoredChunk] = []
    for doc in docs:
        pieces = chunking.chunk_text(doc.text, max_chars=max_chars, overlap=overlap)
        for i, piece in enumerate(pieces):
            chunks.append(
                vectorstore.StoredChunk(
                    id=f"{doc.id}::{i}",
                    text=piece,
                    metadata={
                        "title": doc.title,
                        "source": doc.source,
                        "url": doc.url,
                        "field_id": doc.field_id or "",
                        "level_tags": ",".join(doc.level_tags),
                    },
                )
            )
    if not chunks:
        return 0

    for start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[start : start + _BATCH_SIZE]
        embeddings = await embed_texts([c.text for c in batch])
        vectorstore.upsert(batch, embeddings)
        logger.info("Ingested %d/%d OER chunks", min(start + _BATCH_SIZE, len(chunks)), len(chunks))
    return len(chunks)
