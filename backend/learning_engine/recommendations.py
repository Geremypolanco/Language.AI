"""Adaptive next-course recommendation: pure functions over a student's
competency scores, curriculum order, and the field catalog — no AI call,
no new content generation, just choosing among what's already built/known.

Scope, deliberately: course-level granularity within one field, using the
sequential prerequisite chain knowledge_graph.py actually populates, plus
suggesting sibling specializations (AcademicField.base_field_id) of the
student's current field. This covers "omitir contenido ya dominado",
"recomendar refuerzos", and "sugerir especializaciones" for real. It does
NOT do goal-driven cross-field path planning ("quiero ser AI Engineer, ya
sé Python, empieza en Estructuras de Datos") — that needs either a curated
goal->field/course mapping or an AI planning step, neither of which exists
yet. This is a clean extension point on top of the same competency data,
not a redesign: a future goal-planner would still just be calling
is_mastered()/get_competencies() the same way this module does.
"""

from __future__ import annotations

from .. import academy
from ..models import AcademicField
from . import competency

# Score bands for difficulty_signal — deliberately just a classification
# over existing competency data, not a lever that generates new easier/
# harder content (the pre-generated library has exactly one quiz/exam per
# course; producing real difficulty-scaled variants would mean generating
# and validating several times more content per course during the build,
# which is a build-pipeline change, not a recommendation-engine one).
_REINFORCE_BELOW = 0.5
_ADVANCE_ABOVE = 0.8


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


def suggest_specializations(field_id: str) -> list[AcademicField]:
    """Sibling fields whose base_field_id points at field_id — e.g.
    "artificial-intelligence" and "cybersecurity" both specialize on
    "computer-science". Not gated on mastery: this is an exploratory "you
    could branch into..." suggestion, not an unlock."""
    return [f for f in academy.all_fields() if f.base_field_id == field_id]


def difficulty_signal(user_id: str, course_id: str) -> str:
    """Classifies a student's standing on one course into "reforzar"
    (competency below _REINFORCE_BELOW — needs review before moving on),
    "avanzar" (above _ADVANCE_ABOVE — ready for harder material), or
    "constante" (steady progress, no signal either way). Purely a read of
    existing competency data — see this module's docstring for why it
    doesn't (yet) generate actual harder/easier content."""
    comp = competency.get_competency(user_id, course_id)
    if comp is None:
        return "constante"
    if comp["score"] < _REINFORCE_BELOW:
        return "reforzar"
    if comp["score"] > _ADVANCE_ABOVE:
        return "avanzar"
    return "constante"
