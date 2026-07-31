"""Paragraph-aware text chunking for the OER pipeline.

A deliberately small, dependency-free splitter — the app doesn't otherwise
depend on a framework like LangChain/LlamaIndex, and chunking text into
roughly-even, slightly-overlapping pieces doesn't need one.
"""

from __future__ import annotations

import re


def chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Splits `text` into chunks of at most `max_chars`, preferring paragraph
    boundaries. A paragraph longer than `max_chars` is further split on
    sentence boundaries. Consecutive chunks overlap by `overlap` characters
    (taken from the tail of the previous chunk) so a concept split across a
    boundary still appears whole in at least one chunk."""
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(para) <= max_chars:
            current = para
        else:
            chunks.extend(_split_long(para, max_chars))
            current = ""
    if current:
        chunks.append(current)

    if not overlap or len(chunks) < 2:
        return chunks

    overlapped = [chunks[0]]
    for chunk in chunks[1:]:
        prev_tail = overlapped[-1][-overlap:]
        overlapped.append(f"{prev_tail}\n\n{chunk}" if prev_tail else chunk)
    return overlapped


def _split_long(text: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    current = ""
    for sent in sentences:
        candidate = f"{current} {sent}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                out.append(current)
            current = sent[:max_chars]
    if current:
        out.append(current)
    return out
