"""Calls the AI model to produce one unit's exercise batch, validates the
result, and retries a bounded number of times before giving up — the
"reintentar automáticamente" requirement, applied to language content the
same way academy_library.generators applies it to academic content.

Deliberately bypasses hf_client.generate_exercises — the on-demand path
routers/lessons.py still falls back to for any unit the build hasn't
covered yet (see build.py's module docstring). That path is single-shot
(no retry beyond the one built into chat() itself) and, critically,
personalizes on interests/recent_mistakes: build-time generation here
always passes interests=[] and recent_mistakes=[], so every student
studying a given unit gets byte-identical content — "el contenido
pertenece al curso, no al usuario."
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import curriculum
from ..ai import ai_orchestrator
from ..hf_client import _parse_exercises, _with_teaching_intros
from ..models import Exercise
from . import validators

if TYPE_CHECKING:
    from ..curriculum import Unit

_MAX_ATTEMPTS = 3


class GenerationError(Exception):
    """Raised when a unit's exercises still fail validation after every retry."""


async def generate_unit_exercises(unit: "Unit", target_lang: str, native_lang: str) -> list[Exercise]:
    """The raw, un-wrapped exercise list for a unit (no teaching-intro
    cards yet — see build.py, which wraps this before persisting the
    "content" asset and derives flashcards from the un-wrapped list)."""
    req = curriculum.LessonRequest(
        unit=unit, native_lang=native_lang, target_lang=target_lang, interests=[], recent_mistakes=[]
    )
    prompt = curriculum.build_exercise_generation_prompt(req)

    last_problems: list[str] = ["no attempt made"]
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = await ai_orchestrator.llm.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
            )
            exercises = _parse_exercises(raw)
            problems = validators.validate_exercise_list(exercises)
        except Exception as exc:  # JSON parse failure, network failure, etc.
            exercises, problems = [], [f"attempt {attempt} raised {exc!r}"]
        if not problems:
            return exercises
        last_problems = problems
    raise GenerationError(f"failed after {_MAX_ATTEMPTS} attempts: {'; '.join(last_problems)}")


def wrap_with_teaching_intros(exercises: list[Exercise]) -> list[Exercise]:
    """Re-exported for build.py's convenience — the exact same teach-
    before-quiz wrapping the on-demand path already applies (see
    hf_client._with_teaching_intros), so a pre-built unit's shape matches
    what an on-demand-generated one has always looked like."""
    return _with_teaching_intros(exercises)


def build_flashcards(exercises: list[Exercise]) -> list[dict]:
    """Derives a flashcard set directly from already-generated exercises —
    no extra AI call, deduplicated by vocab_key. Deliberately does NOT
    include an IPA phonetic transcription: producing an accurate one for
    an arbitrary target language needs either a verified phonetic
    dictionary or a specialized model, neither of which this app has
    integrated, and an unverified, possibly-wrong IPA string would
    actively mislead a learner — worse than omitting it entirely.
    audio_text (already real, TTS-backed pronunciation elsewhere in the
    app) covers "how does this actually sound" instead."""
    seen: set[str] = set()
    cards: list[dict] = []
    for ex in exercises:
        if not ex.vocab_key or ex.vocab_key in seen or not ex.target_text:
            continue
        seen.add(ex.vocab_key)
        cards.append(
            {
                "vocab_key": ex.vocab_key,
                "target_text": ex.target_text,
                "native_text": ex.native_text,
                "audio_text": ex.audio_text or ex.target_text,
                "image_prompt": ex.image_prompt,
            }
        )
    return cards
