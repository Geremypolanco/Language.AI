"""Blocker detection: when a student is struggling somewhere, walk the
knowledge graph's real edges backward to find the more likely root cause,
at two levels of granularity:

- Course-level (find_blockers/likely_root_cause): the course-level
  "prerequisite_of" chain knowledge_graph.py derives from curriculum
  order alone, zero extra AI cost.
- Concept-level (find_concept_blockers/likely_concept_root_cause): the
  fine-grained "depends_on" edges academy_library.generators.
  generate_concept_relations extracts per course at build time (see
  scripts/build_academy.py) — e.g. "Trees" -> "Recursion" -> "Functions"
  -> "Variables", not just "the course before this one." A concept is
  "weak" here using the exact same status buckets mentor_engine/
  knowledge_profile.py already computes from real SM-2 review state —
  no second definition of "struggling."

Both reuse the exact graph/profile already built elsewhere; this module
only walks edges and reads statuses, it never writes either.
"""

from __future__ import annotations

from ..learning_engine import competency, knowledge_graph
from . import knowledge_profile

_WEAK_THRESHOLD = 0.5
_WEAK_CONCEPT_STATUSES = ("unknown", "learning")


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


def find_concept_blockers(user_id: str, concept_id: str) -> list[dict]:
    """The student's weak (unknown/learning) prerequisite CONCEPTS for
    `concept_id` — e.g. if the student keeps failing on "Trees" and
    "Trees" was extracted as depending on "Recursion", and the student's
    own knowledge profile still shows "Recursion" as unknown/learning,
    that's returned here. Empty when this concept has no extracted
    dependency yet (extraction hasn't run for this course pair, or the
    model genuinely found none) or every prerequisite concept is solid."""
    blockers = []
    for prereq_id in knowledge_graph.prerequisite_concepts(concept_id):
        status = knowledge_profile.get_concept_status(user_id, prereq_id)
        if status in _WEAK_CONCEPT_STATUSES:
            blockers.append({"concept_id": prereq_id, "status": status})
    return blockers


def likely_concept_root_cause(user_id: str, concept_id: str) -> dict | None:
    """The single most-likely-culprit prerequisite concept — "unknown"
    outranks "learning" as a cause worth naming first, since it means the
    student has never even encountered it yet."""
    blockers = find_concept_blockers(user_id, concept_id)
    if not blockers:
        return None
    status_rank = {"unknown": 0, "learning": 1}
    return min(blockers, key=lambda b: status_rank.get(b["status"], 99))
