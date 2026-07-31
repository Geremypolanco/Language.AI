import asyncio

from backend.streaming import stream_audio_payloads


async def _fake_stream(chunks: list[str]):
    for chunk in chunks:
        yield chunk


def _collect(text_stream, synthesize):
    async def run():
        return [chunk async for chunk in stream_audio_payloads(text_stream, synthesize)]

    return asyncio.run(run())


def test_yields_audio_as_soon_as_each_sentence_completes():
    seen_sentences = []

    async def synthesize(sentence: str):
        seen_sentences.append(sentence)
        return sentence.encode()

    # Tokens arrive in small, arbitrarily-split pieces, as a real streaming
    # LLM response would deliver them — not aligned to sentence boundaries.
    tokens = ["Hola", ", ¿cómo", " estás", "? Bien", ", gracias", "! Vamos a", " empezar."]
    results = _collect(_fake_stream(tokens), synthesize)

    assert seen_sentences == ["Hola, ¿cómo estás?", "Bien, gracias!", "Vamos a empezar."]
    assert results == [s.encode() for s in seen_sentences]


def test_flushes_a_trailing_sentence_with_no_closing_punctuation():
    seen_sentences = []

    async def synthesize(sentence: str):
        seen_sentences.append(sentence)
        return b"AUDIO"

    tokens = ["Esto termina", " sin puntuacion"]
    _collect(_fake_stream(tokens), synthesize)

    assert seen_sentences == ["Esto termina sin puntuacion"]


def test_skips_yielding_when_synthesize_fails_for_one_sentence_but_keeps_going():
    async def synthesize(sentence: str):
        if sentence == "Falla.":
            return None
        return sentence.encode()

    tokens = ["Bien. ", "Falla. ", "Sigue."]
    results = _collect(_fake_stream(tokens), synthesize)

    assert results == [b"Bien.", b"Sigue."]


def test_empty_stream_yields_nothing():
    async def synthesize(sentence: str):
        raise AssertionError("synthesize should never be called for an empty stream")

    results = _collect(_fake_stream([]), synthesize)
    assert results == []


def test_semicolons_and_exclamation_marks_also_flush_a_chunk():
    seen_sentences = []

    async def synthesize(sentence: str):
        seen_sentences.append(sentence)
        return b"AUDIO"

    tokens = ["Primero", "; segundo", "! tercero."]
    _collect(_fake_stream(tokens), synthesize)

    assert seen_sentences == ["Primero;", "segundo!", "tercero."]
