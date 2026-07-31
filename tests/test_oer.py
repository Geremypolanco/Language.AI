import asyncio

from backend.oer import chunking, ingest, retrieval, vectorstore
from backend.oer.sources import OERDocument


def test_chunk_text_empty_string_returns_no_chunks():
    assert chunking.chunk_text("") == []
    assert chunking.chunk_text("   ") == []


def test_chunk_text_keeps_short_text_as_a_single_chunk():
    text = "One short paragraph that easily fits in a single chunk."
    assert chunking.chunk_text(text, max_chars=900) == [text]


def test_chunk_text_splits_long_text_on_paragraph_boundaries():
    paragraphs = [f"Paragraph {i}: some padding text to give it real length." for i in range(12)]
    text = "\n\n".join(paragraphs)

    chunks = chunking.chunk_text(text, max_chars=120, overlap=0)

    assert len(chunks) > 1
    # every paragraph's marker text shows up somewhere across the chunks
    joined = "\n\n".join(chunks)
    for i in range(12):
        assert f"Paragraph {i}:" in joined


def test_chunk_text_overlap_repeats_the_tail_of_the_previous_chunk():
    paragraphs = [f"Paragraph {i}: some padding text to give it real length." for i in range(12)]
    text = "\n\n".join(paragraphs)

    chunks = chunking.chunk_text(text, max_chars=120, overlap=30)

    assert len(chunks) > 1
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.startswith(prev[-30:])


def test_chunk_text_splits_a_single_oversized_paragraph_on_sentences():
    sentence = "This is one sentence in a very long paragraph that has no double newlines at all. "
    text = sentence * 20  # a single "paragraph" far longer than max_chars

    chunks = chunking.chunk_text(text, max_chars=200, overlap=0)

    assert len(chunks) > 1
    assert all(len(c) <= 210 for c in chunks)  # small slack for the last sentence in a chunk


def _run(coro):
    return asyncio.run(coro)


def test_ingest_and_retrieve_round_trip():
    docs = [
        OERDocument(
            id="test:finance-basics",
            title="Fundamentos de finanzas",
            text="Planificar un presupuesto personal es la base de la gestión financiera.",
            source="test",
            url="https://example.com/finance",
            field_id="finance",
        ),
        OERDocument(
            id="test:biology-basics",
            title="Fundamentos de biología",
            text="La célula es la unidad estructural y funcional de todo ser vivo.",
            source="test",
            url="https://example.com/biology",
            field_id="biology",
        ),
    ]

    chunk_count = _run(ingest.ingest_documents(docs))
    assert chunk_count == 2
    assert vectorstore.count() == 2

    # The offline pseudo-embeddings (see hf_client._offline_embedding) aren't
    # semantically meaningful, so a query in different words than the stored
    # text can't reliably clear a real similarity threshold here — min_similarity=0
    # isolates "does the pipeline wire up correctly" from "is 0.82 the right bar",
    # which is a separate, dedicated test below.
    hits = _run(
        retrieval.retrieve_context("presupuesto y gestión financiera", field_id="finance", k=3, min_similarity=0.0)
    )
    assert len(hits) >= 1
    assert any(h.title == "Fundamentos de finanzas" for h in hits)


def test_retrieve_context_never_bleeds_across_fields():
    """The isolation guarantee: a field with nothing ingested must return
    empty, never another field's chunks — no silent cross-field fallback."""
    docs = [
        OERDocument(
            id="test:only-biology",
            title="Fundamentos de biología",
            text="La célula es la unidad estructural y funcional de todo ser vivo.",
            source="test",
            url="https://example.com/biology",
            field_id="biology",
        ),
    ]
    _run(ingest.ingest_documents(docs))

    hits = _run(retrieval.retrieve_context("cualquier consulta", field_id="history", k=3, min_similarity=0.0))
    assert hits == []


def test_retrieve_context_rejects_hits_below_the_similarity_threshold():
    docs = [
        OERDocument(
            id="test:exact-match",
            title="Coincidencia exacta",
            text="texto de prueba para similitud",
            source="test",
            url="https://example.com/x",
            field_id="finance",
        ),
    ]
    _run(ingest.ingest_documents(docs))

    # Querying with the exact same text the offline embedder saw guarantees
    # similarity == 1.0 (identical hash-based vector), a reliable way to
    # exercise the threshold logic without needing real embeddings.
    high_bar_hits = _run(
        retrieval.retrieve_context("texto de prueba para similitud", field_id="finance", k=3, min_similarity=0.999)
    )
    assert len(high_bar_hits) == 1

    impossible_bar_hits = _run(
        retrieval.retrieve_context("texto de prueba para similitud", field_id="finance", k=3, min_similarity=1.1)
    )
    assert impossible_bar_hits == []


def test_retrieve_context_on_empty_store_returns_no_hits():
    hits = _run(retrieval.retrieve_context("consulta sin datos ingeridos", k=3, min_similarity=0.0))
    assert hits == []
