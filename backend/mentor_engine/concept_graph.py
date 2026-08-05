"""Concept/course blocker detection: when a student is weak on a course,
walk the knowledge graph's real prerequisite_of edges (learning_engine/
knowledge_graph.py, populated from actual curriculum order) backward to
find which prerequisite course is the more likely root cause — reusing
the exact graph already built, not a second relation type or a parallel
graph structure.

Scoped to COURSE-level prerequisites, matching what knowledge_graph.py
actually populates today (see its own docstring): a fine-grained concept-
to-concept graph like "Recursion -> Trees" would need either manual
curation or a dedicated AI extraction pass over course content, neither
of which exists yet. This module is written against knowledge_graph's
public functions only, so plugging in a finer-grained graph later
(concept_graph.RELATION_TYPES already reserves "depends_on" for exactly
this) doesn't require changing find_blockers' shape.
"""

from __future__ import annotations

from ..learning_engine import competency, knowledge_graph

_WEAK_THRESHOLD = 0.5


def find_blockers(user_id: str, course_id: str) -> list[dict]:
    """The student's weak-or-unattempted prerequisite courses for
    `course_id` — the working theory being that struggling here is more
    likely a gap earlier in the chain than a problem with this course
    itself. Empty when the course has no recorded prerequisite or every
    prerequisite is already solid."""
    blockers = []
    for prereq_id in knowledge_graph.prerequisite_courses(course_id):
        comp = competency.get_competency(user_id, prereq_id)
        score = comp["score"] if comp else None
        if score is None or score < _WEAK_THRESHOLD:
            blockers.append({"course_id": prereq_id, "score": score})
    return blockers


def likely_root_cause(user_id: str, course_id: str) -> dict | None:
    """The single weakest prerequisite, if any — what a mentor would
    actually say out loud ("probablemente necesitas reforzar X") instead
    of listing every blocker at once."""
    blockers = find_blockers(user_id, course_id)
    if not blockers:
        return None
    return min(blockers, key=lambda b: b["score"] if b["score"] is not None else -1.0)
