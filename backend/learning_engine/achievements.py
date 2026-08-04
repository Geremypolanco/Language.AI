"""Real, skill-backed achievements — never a cosmetic-only badge (the
request's own example: "Mastered Binary Trees", not "logged in 5 days in a
row"). Every achievement here is DERIVED from data already tracked
elsewhere (competency scores, completed courses), computed on read rather
than stored as its own mutable state — an achievement can never drift out
of sync with what actually happened, because it isn't a separate fact,
it's a query over facts the app already trusts.
"""

from __future__ import annotations

from .. import db
from . import competency

_COMPLETION_MILESTONES = (5, 10, 25, 50, 100)


def mastered_course_achievements(user_id: str, field_id: str, course_titles: dict[str, str] | None = None) -> list[dict]:
    titles = course_titles or {}
    return [
        {
            "id": f"mastered:{c['course_id']}",
            "title": f"Dominado: {titles.get(c['course_id'], c['course_id'])}",
            "kind": "mastery",
            "course_id": c["course_id"],
        }
        for c in competency.get_competencies(user_id, field_id)
        if c["score"] >= competency.MASTERY_THRESHOLD
    ]


def completion_achievements(user_id: str) -> list[dict]:
    """Milestone badges at meaningful thresholds — one badge per course
    completed would just be noise, not a real accomplishment marker."""
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM academy_course_progress WHERE user_id=?", (user_id,))
        completed = cur.fetchone()["c"]
    return [
        {"id": f"completed:{m}", "title": f"{m} cursos completados", "kind": "completion", "threshold": m}
        for m in _COMPLETION_MILESTONES
        if completed >= m
    ]


def achievements_for(user_id: str, field_id: str, course_titles: dict[str, str] | None = None) -> list[dict]:
    return mastered_course_achievements(user_id, field_id, course_titles) + completion_achievements(user_id)
