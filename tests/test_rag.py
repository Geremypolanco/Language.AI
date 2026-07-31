"""Tests for backend/rag.py — kept fully offline (no real arxiv.org calls)
by testing the pure XML-parsing/formatting helpers directly and by relying
on fetch_arxiv_context's own hf_configured-style guard (unmapped fields
return "" without ever touching the network)."""

import asyncio

from backend.rag import (
    ARXIV_CATEGORY_FOR_FIELD,
    _format_arxiv_context,
    fetch_arxiv_context,
    parse_arxiv_atom,
)

_SAMPLE_ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <summary>  We propose a new simple network architecture, the Transformer,
    based solely on attention mechanisms.  </summary>
  </entry>
  <entry>
    <title>Deep Residual Learning</title>
    <summary>We present a residual learning framework.</summary>
  </entry>
</feed>
"""

_EMPTY_ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""


def test_parse_arxiv_atom_extracts_title_and_summary_pairs():
    papers = parse_arxiv_atom(_SAMPLE_ATOM)
    assert len(papers) == 2
    assert papers[0][0] == "Attention Is All You Need"
    assert "Transformer" in papers[0][1]
    # whitespace/newlines inside the XML text are collapsed
    assert "\n" not in papers[0][1]


def test_parse_arxiv_atom_handles_no_entries():
    assert parse_arxiv_atom(_EMPTY_ATOM) == []


def test_format_arxiv_context_empty_when_no_papers():
    assert _format_arxiv_context([]) == ""


def test_format_arxiv_context_includes_titles_and_grounding_instruction():
    context = _format_arxiv_context([("Some Paper", "A short summary.")])
    assert "Some Paper" in context
    assert "A short summary." in context
    assert "arXiv" in context


def test_every_arxiv_mapped_field_id_is_a_plausible_slug():
    # sanity check on the mapping itself, not a network call
    assert len(ARXIV_CATEGORY_FOR_FIELD) > 0
    for field_id, category in ARXIV_CATEGORY_FOR_FIELD.items():
        assert field_id
        assert category


def test_fetch_arxiv_context_returns_empty_for_unmapped_field_without_network():
    # "music" has no arXiv coverage — must short-circuit before any request
    result = asyncio.run(fetch_arxiv_context("music", "Music theory basics"))
    assert result == ""
