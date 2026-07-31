"""Thin OER-pipeline entry point for embeddings — delegates to
HFClient.embed_texts so all HF Inference API calls stay centralized in
hf_client.py (same reasoning as academy.py/library.py delegating their
generation calls there)."""

from __future__ import annotations

from ..hf_client import hf_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    return await hf_client.embed_texts(texts)
