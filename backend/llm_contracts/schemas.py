"""LLM output contracts — validated schemas for every structured output an
LLM is allowed to produce inside Language.AI.

Python port of the llm-contracts standard (pydantic instead of zod):
fixed shapes, bounded strings, enums for closed vocabularies, numeric
ranges. Mirrors the anti-hallucination rule — an LLM result that fails
validation is retried (see validate.py) and, if it still fails, routed to
the dead-letter queue (see dead_letter.py). We NEVER invent or pad data to
make a schema pass.

U3 note: parsing an LLM's raw JSON into these models is the edge; the
converters that turn a validated contract into domain objects
(Exercise, Recommendation dicts, …) live next to the call sites as pure,
deterministic functions — the LLM never constructs domain objects.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, RootModel, TypeAdapter, field_validator

from ..models import ExerciseType


class RecommendationKind(StrEnum):
    book = "book"
    song = "song"
    podcast = "podcast"
    show = "show"


class ExerciseJSON(BaseModel):
    """One raw exercise item exactly as the exercise-generation prompt asks
    the model to emit it. `id` is NOT trusted from the model — the caller
    assigns it deterministically (see _exercise_from_contract in
    hf_client.py); `vocab_key` is required so the item stays attributable.
    Extra keys the model adds are ignored, never acted on."""

    type: ExerciseType
    prompt: str = Field(default="", max_length=2000)
    target_text: str = Field(min_length=1, max_length=2000)
    native_text: str = Field(default="", max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=12)
    correct_answer: str = Field(default="", max_length=2000)
    image_prompt: str = Field(default="", max_length=1000)
    audio_text: str = Field(default="", max_length=2000)
    vocab_key: str = Field(min_length=1, max_length=200)


EXERCISE_LIST: TypeAdapter[list[ExerciseJSON]] = TypeAdapter(list[ExerciseJSON])


class ReviewExerciseJSON(BaseModel):
    """Like ExerciseJSON, but for spaced-repetition review items the model
    is never trusted with identity at all: no vocab_key, no id — those are
    force-assigned from the caller's due-items list by position. Every
    content field is optional-with-default so a partial item degrades to
    the known-good snapshot instead of failing the whole batch; an EMPTY
    list still fails (min_length=1 on the list adapter)."""

    type: ExerciseType = ExerciseType.TRANSLATE_TO_NATIVE
    prompt: str = Field(default="", max_length=2000)
    target_text: str = Field(default="", max_length=2000)
    native_text: str = Field(default="", max_length=2000)
    correct_answer: str = Field(default="", max_length=2000)
    audio_text: str = Field(default="", max_length=2000)


def _bounded_review_list() -> TypeAdapter[list[ReviewExerciseJSON]]:
    from typing import Annotated

    from pydantic import Field as _Field

    BoundedList = Annotated[list[ReviewExerciseJSON], _Field(min_length=1)]
    return TypeAdapter(BoundedList)


REVIEW_EXERCISE_LIST: TypeAdapter[list[ReviewExerciseJSON]] = _bounded_review_list()


class AssignmentGrade(BaseModel):
    """Qualitative grade for a submitted tarea/informe/proyecto."""

    grade: str = Field(min_length=1, max_length=80)
    feedback: str = Field(min_length=1, max_length=2000)


class OpenAnswerGrade(BaseModel):
    """Grade for one open/applied_problem quiz or exam question.

    `passed` is a REAL bool — this is load-bearing: the old code did
    `bool(data.get("passed"))`, and in Python the string "false" is
    truthy, so a model writing {"passed": "false"} was graded as PASSED.
    The contract rejects non-bool values outright."""

    passed: bool
    feedback: str = Field(min_length=1, max_length=500)


class RecommendationItem(BaseModel):
    """One suggested book/song/podcast/show. Shape-bounded; note the
    residual risk documented in ANTI-HALLUCINATION-AUDIT.md — no offline
    oracle exists for "does this title really exist", so the contract
    enforces honesty of shape, and the prompt carries the do-not-invent
    instruction."""

    kind: RecommendationKind
    title: str = Field(min_length=1, max_length=200)
    creator: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=300)


def _bounded_recommendation_list() -> TypeAdapter[list[RecommendationItem]]:
    from typing import Annotated

    from pydantic import Field as _Field

    BoundedList = Annotated[list[RecommendationItem], _Field(min_length=1, max_length=12)]
    return TypeAdapter(BoundedList)


RECOMMENDATION_LIST: TypeAdapter[list[RecommendationItem]] = _bounded_recommendation_list()


class NewsArticle(BaseModel):
    """One generated news summary. Bounded; translation may be empty."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1500)
    translation: str = Field(default="", max_length=1500)


def _bounded_news_list() -> TypeAdapter[list[NewsArticle]]:
    from typing import Annotated

    from pydantic import Field as _Field

    BoundedList = Annotated[list[NewsArticle], _Field(min_length=1, max_length=10)]
    return TypeAdapter(BoundedList)


NEWS_LIST: TypeAdapter[list[NewsArticle]] = _bounded_news_list()


class NonEmptyText(RootModel[str]):
    """Gate for free-text LLM outputs (tutor replies, feedback, memory
    summaries, explanations): the text must exist and be bounded. It says
    nothing about truth — free text is never acted on as fact."""

    root: str = Field(min_length=1, max_length=8000)

    @field_validator("root", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        # Whitespace-only output is empty output — it must fail the gate,
        # not get stored as someone's long-term memory.
        return value.strip() if isinstance(value, str) else value


NON_EMPTY_TEXT: TypeAdapter[NonEmptyText] = TypeAdapter(NonEmptyText)
