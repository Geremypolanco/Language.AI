"""Content-quality gates the build pipeline runs before persisting a
unit's generated exercises — same "catch a bad AI output before it's
published" role as academy_library.validators, applied to
backend.models.Exercise's shape instead of academy's JSON dicts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Exercise

_GRADED_CHOICE_TYPES = {"multiple_choice", "image_match"}


def validate_exercise_list(exercises: list["Exercise"], min_count: int = 1) -> list[str]:
    if not exercises or len(exercises) < min_count:
        return [f"expected at least {min_count} exercises, got {len(exercises) if exercises else 0}"]

    problems: list[str] = []
    for i, ex in enumerate(exercises):
        if not ex.target_text and not ex.prompt:
            problems.append(f"exercise {i} has neither target_text nor prompt")
        if ex.type.value in _GRADED_CHOICE_TYPES and len(ex.options) < 2:
            problems.append(f"exercise {i} ({ex.type.value}) needs at least 2 options")
        if not ex.vocab_key:
            problems.append(f"exercise {i} is missing a vocab_key")
    return problems


def validate_flashcards(cards: list[dict]) -> list[str]:
    problems: list[str] = []
    for i, card in enumerate(cards):
        if not card.get("target_text"):
            problems.append(f"flashcard {i} is missing target_text")
        if not card.get("vocab_key"):
            problems.append(f"flashcard {i} is missing vocab_key")
    return problems
