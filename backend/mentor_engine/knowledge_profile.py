"""Knowledge Profile: a concept-by-concept mastery map, built entirely
from data that already exists — the knowledge graph's concepts
(learning_engine/knowledge_graph.py, derived from real course glossaries)
and each concept's own spaced-repetition state (learning_engine/
concept_review.py, which reuses backend/srs.py's SM-2 engine for academic
concepts the exact same way it already does for language vocabulary).

No new tracking table, no manual "mark this as learned" UI: every concept
the student has ever reviewed already has enough signal in vocab_progress
to classify, and this module just reads it.

Status buckets are a deterministic, documented reading of real SM-2
state — not a machine-learned classification:
- unknown: never reviewed at all (no vocab_progress row).
- learning: reviewed, but 2 or fewer successful repetitions so far.
- practicing: 3-5 successful repetitions.
- mastered: 6+ repetitions, with at least one past mistake along the way.
- expert: 6+ repetitions and zero mistakes ever, with SM-2's own ease
  factor still at (or above) its starting value — its own signal that
  this concept has needed the least reinforcement of any reviewed term.
"""

from __future__ import annotations

from .. import db
from ..learning_engine import knowledge_graph

_LEARNING_MAX_REPS = 2
_PRACTICING_MAX_REPS = 5
_EXPERT_MIN_EASE = 2.5
_ACADEMIC_PREFIX = "academic:"


def _status_from_row(row: dict | None) -> str:
    if row is None:
        return "unknown"
    reps = row["repetitions"]
    if reps <= _LEARNING_MAX_REPS:
        return "learning"
    if reps <= _PRACTICING_MAX_REPS:
        return "practicing"
    if row["mistake_count"] == 0 and row["ease_factor"] >= _EXPERT_MIN_EASE:
        return "expert"
    return "mastered"


def get_knowledge_profile(user_id: str, field_id: str) -> list[dict]:
    """One entry per concept in the field's knowledge graph, grouped by
    course_id at the call site if the caller wants a "Computer Science ->
    Variables, Functions, ..." tree — this returns the flat list with
    enough fields (course_id, term, status) to build that grouping without
    a second query."""
    concepts = knowledge_graph.concepts_for_field(field_id)
    if not concepts:
        return []

    with db.cursor() as cur:
        cur.execute(
            "SELECT vocab_key, repetitions, mistake_count, ease_factor FROM vocab_progress "
            "WHERE user_id=? AND vocab_key LIKE ?",
            (user_id, f"{_ACADEMIC_PREFIX}%"),
        )
        by_concept_id = {r["vocab_key"][len(_ACADEMIC_PREFIX):]: r for r in cur.fetchall()}

    return [
        {
            "concept_id": c["id"],
            "course_id": c["course_id"],
            "term": c["term"],
            "status": _status_from_row(by_concept_id.get(c["id"])),
        }
        for c in concepts
    ]


def weak_concepts(user_id: str, field_id: str) -> list[dict]:
    """Concepts still "unknown" or "learning" — the ones a Daily Plan or
    Mentor Insight would actually want to call out by name."""
    return [c for c in get_knowledge_profile(user_id, field_id) if c["status"] in ("unknown", "learning")]


def get_concept_status(user_id: str, concept_id: str) -> str:
    """Single-concept lookup — used by mentor_engine/concept_graph.py's
    concept-level blocker detection, which needs one prerequisite
    concept's status at a time rather than a whole field's profile."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT repetitions, mistake_count, ease_factor FROM vocab_progress WHERE user_id=? AND vocab_key=?",
            (user_id, f"{_ACADEMIC_PREFIX}{concept_id}"),
        )
        row = cur.fetchone()
    return _status_from_row(dict(row) if row else None)
