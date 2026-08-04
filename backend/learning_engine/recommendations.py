"""Adaptive next-course recommendation: a pure function over a student's
competency scores and curriculum order — no AI call, no new content
generation, just choosing which already-built course to study next.

Scope, deliberately: course-level granularity within one field, using the
sequential prerequisite chain knowledge_graph.py actually populates. This
covers "omitir contenido ya dominado" and "recomendar refuerzos" for real.
It does NOT do goal-driven cross-field path planning ("quiero ser AI
Engineer, ya sé Python, empieza en Estructuras de Datos") — that needs
either a curated goal->field/course mapping or an AI planning step, neither
of which exists yet. This is a clean extension point on top of the same
competency data, not a redesign: a future goal-planner would still just be
calling is_mastered()/get_competencies() the same way this module does.
"""

from __future__ import annotations

from . import competency


def recommend_next_course(user_id: str, field_id: str, course_ids_in_order: list[str]) -> str | None:
    """The earliest not-yet-mastered course in curriculum order — skips
    anything the student has already demonstrated mastery of. Returns None
    once every course is mastered (nothing left to recommend)."""
    for course_id in course_ids_in_order:
        if not competency.is_mastered(user_id, course_id):
            return course_id
    return None


def courses_needing_review(
    user_id: str, field_id: str, course_ids_in_order: list[str], weak_threshold: float = 0.6
) -> list[str]:
    """Courses the student has attempted but scored below weak_threshold on
    — worth reinforcing even though they've moved past them in curriculum
    order. Ordered by curriculum position, not by how weak they are, so a
    student sees them in the same sequence they originally studied them."""
    scores = {c["course_id"]: c["score"] for c in competency.get_competencies(user_id, field_id)}
    return [cid for cid in course_ids_in_order if cid in scores and scores[cid] < weak_threshold]
