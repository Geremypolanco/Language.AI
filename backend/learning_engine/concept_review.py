"""Spaced-repetition review of academic concepts — reuses the exact SM-2
engine backend/srs.py already runs for language vocabulary rather than
building a second one: srs.schedule_review's vocab_key was always just an
opaque string, so an academic concept's own id (course_id::term-slug, see
knowledge_graph.py) works as a vocab_key with zero changes to srs.py
itself beyond the key_prefix/exclude_prefix filter due_review_items now
takes to keep the two review flows from bleeding into each other.

No AI call needed here at all, unlike the language Repaso feature: a
concept's term + definition (captured once, when the knowledge graph was
built from the course's glossary) IS the whole review — recalling a
technical term's exact definition is the actual goal, not recombining it
into a fresh sentence the way language vocabulary review does.
"""

from __future__ import annotations

from .. import srs

_PREFIX = "academic:"


def concept_vocab_key(concept_id: str) -> str:
    return f"{_PREFIX}{concept_id}"


def is_concept_vocab_key(vocab_key: str) -> bool:
    return vocab_key.startswith(_PREFIX)


def concept_id_from_vocab_key(vocab_key: str) -> str:
    if not is_concept_vocab_key(vocab_key):
        raise ValueError(f"not an academic concept vocab_key: {vocab_key!r}")
    return vocab_key[len(_PREFIX):]


def record_answer(user_id: str, concept_id: str, correct: bool, concept_term: str, concept_definition: str) -> dict:
    quality = srs.grade_to_quality(correct)
    return srs.schedule_review(user_id, concept_vocab_key(concept_id), quality, concept_term, concept_definition)


def due_concepts(user_id: str, limit: int = 10) -> list[dict]:
    """Due concept flashcards: {vocab_key, target_text (the term),
    native_text (the definition)} — the caller strips the "academic:"
    prefix back off vocab_key to recover the raw concept id if needed."""
    return srs.due_review_items(user_id, limit=limit, key_prefix=_PREFIX)
