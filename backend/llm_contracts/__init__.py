"""Anti-hallucination contracts for LLM outputs (U2/U3/U5).

Every structured LLM output in the app is validated against a pydantic
contract via validate_or_retry(); persistent failures land in the
dead-letter queue for triage — never silently in front of the learner,
never invented.
"""

from .citations import (
    CITATION_RE,
    CitationError,
    grounding_citations,
    is_valid_citation,
    require_citations,
    source_to_citation,
)
from .dead_letter import DeadLetterEntry, DeadLetterQueue, dead_letters
from .schemas import (
    EXERCISE_LIST,
    NEWS_LIST,
    NON_EMPTY_TEXT,
    RECOMMENDATION_LIST,
    REVIEW_EXERCISE_LIST,
    AssignmentGrade,
    ExerciseJSON,
    NewsArticle,
    NonEmptyText,
    OpenAnswerGrade,
    RecommendationItem,
    RecommendationKind,
    ReviewExerciseJSON,
)
from .validate import validate_or_retry

__all__ = [
    "CITATION_RE",
    "CitationError",
    "grounding_citations",
    "is_valid_citation",
    "require_citations",
    "source_to_citation",
    "DeadLetterEntry",
    "DeadLetterQueue",
    "dead_letters",
    "EXERCISE_LIST",
    "NEWS_LIST",
    "NON_EMPTY_TEXT",
    "RECOMMENDATION_LIST",
    "REVIEW_EXERCISE_LIST",
    "AssignmentGrade",
    "ExerciseJSON",
    "NewsArticle",
    "NonEmptyText",
    "OpenAnswerGrade",
    "RecommendationItem",
    "RecommendationKind",
    "ReviewExerciseJSON",
    "validate_or_retry",
]
