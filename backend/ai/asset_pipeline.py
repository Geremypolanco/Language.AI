"""Offline asset generation: given already-generated text content (glossary
terms, vocabulary flashcards, ...), pre-synthesizes and permanently stores
its audio via SpeechRouter's Offline Voice Builder pipeline. This is the
concrete implementation of "todo contenido educativo debe poder tener audio
asociado," wired directly into the two build pipelines that already
generate content once and serve it forever
(backend/academy_library/build.py, backend/language_library/build.py) — see
AI_ARCHITECTURE.md.

Every function here is best-effort per item: one item's synthesis failing
(HF budget exhausted mid-build, a transient network error, or simply no
Piper voice for that language) is logged and that item is left with
audio_url=None — it never aborts the rest of the build, unlike
academy_library.generators.GenerationError for missing *text* content.
Audio is additive polish on top of already-valid text content, not a
required field, exactly like image_prompt/audio_text already are on
Exercise (backend/models.py)."""

from __future__ import annotations

import logging

from .orchestrator import ai_orchestrator

logger = logging.getLogger("lingua.ai.asset_pipeline")


async def add_glossary_audio(namespace: str, target_lang: str, glossary: dict) -> dict:
    """Adds an `audio_url` to every term in an academy_library glossary
    asset (see academy_library.generators.generate_glossary's {"terms": [...]}
    shape), pronounced in `target_lang` (the academy's content_lang — see
    models.AcademyEnrollment). `namespace` scopes the permanent asset store,
    e.g. f"glossary:{field_id}:{level}"."""
    for term in glossary.get("terms", []):
        word = (term.get("term") or "").strip()
        if not word:
            continue
        try:
            term["audio_url"] = await ai_orchestrator.speech.synthesize_asset(namespace, word, word, target_lang)
        except Exception:
            logger.exception("Glossary audio synthesis failed for %r in %s", word, namespace)
            term["audio_url"] = None
    return glossary


async def add_flashcard_audio(namespace: str, target_lang: str, flashcards: list[dict]) -> list[dict]:
    """Adds an `audio_url` to every flashcard produced by
    language_library.generators.build_flashcards, pronouncing each card's
    audio_text (falling back to target_text, same guarantee build_flashcards
    already makes). `namespace` scopes the permanent asset store, e.g.
    f"flashcards:{pair_key}:{level}:{unit_id}"."""
    for card in flashcards:
        text = (card.get("audio_text") or card.get("target_text") or "").strip()
        vocab_key = card.get("vocab_key") or text
        if not text:
            continue
        try:
            card["audio_url"] = await ai_orchestrator.speech.synthesize_asset(
                namespace, vocab_key, text, target_lang
            )
        except Exception:
            logger.exception("Flashcard audio synthesis failed for %r in %s", vocab_key, namespace)
            card["audio_url"] = None
    return flashcards
