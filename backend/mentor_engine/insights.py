"""Mentor Insights: real, specific observations derived from a student's
actual recent activity — "has mejorado en Probabilidad", "sigues con
dificultades en Recursión" — never a generic "great job!" message. Each
helper below returns an insight only when there's real before/after or
concentration evidence for one; no insight is fabricated to fill space.
"""

from __future__ import annotations

from .. import db
from ..learning_engine import competency, student_profile
from ..learning_engine import recommendations as base_recommendations

_IMPROVEMENT_THRESHOLD = 0.15
_STRUGGLE_THRESHOLD = 0.5


def _quiz_trend_insights(user_id: str, titles: dict) -> list[dict]:
    """Compares each course's two most recent quiz/exam submissions —
    real before/after evidence, not a single snapshot compared to nothing."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT course_id, score FROM academy_quiz_submission WHERE user_id=? ORDER BY course_id, id ASC",
            (user_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    by_course: dict[str, list[float]] = {}
    for r in rows:
        by_course.setdefault(r["course_id"], []).append(r["score"])

    insights = []
    for course_id, scores in by_course.items():
        if len(scores) < 2:
            continue
        title = titles.get(course_id, course_id)
        delta = scores[-1] - scores[-2]
        if delta >= _IMPROVEMENT_THRESHOLD:
            insights.append(
                {
                    "type": "improvement",
                    "message": f"Has mejorado en \"{title}\": pasaste de {scores[-2]:.0%} a {scores[-1]:.0%}.",
                    "evidence": {"course_id": course_id, "previous": scores[-2], "latest": scores[-1]},
                }
            )
        elif scores[-1] < _STRUGGLE_THRESHOLD and scores[-2] < _STRUGGLE_THRESHOLD:
            insights.append(
                {
                    "type": "struggle",
                    "message": f"Todavía tienes dificultades con \"{title}\" — tus últimos dos intentos siguen por debajo del umbral esperado.",
                    "evidence": {"course_id": course_id, "previous": scores[-2], "latest": scores[-1]},
                }
            )
    return insights


def _mistake_concentration_insight(user_id: str, field_id: str, titles: dict) -> dict | None:
    mistakes = student_profile.frequent_mistakes(user_id, field_id, top_n=20)
    if not mistakes:
        return None
    by_course: dict[str, int] = {}
    for m in mistakes:
        by_course[m["course_id"]] = by_course.get(m["course_id"], 0) + m["times_missed"]
    worst_course = max(by_course, key=by_course.get)
    return {
        "type": "mistake_pattern",
        "message": f"Tus errores actuales provienen principalmente de \"{titles.get(worst_course, worst_course)}\".",
        "evidence": {"course_id": worst_course, "missed_count": by_course[worst_course]},
    }


def _mastery_transition_insight(user_id: str, field_id: str, course_ids_in_order: list[str], titles: dict) -> dict | None:
    mastered_ids = [c for c in course_ids_in_order if competency.is_mastered(user_id, c)]
    if not mastered_ids:
        return None
    next_course = base_recommendations.recommend_next_course(user_id, field_id, course_ids_in_order)
    if not next_course:
        return None
    last_mastered = mastered_ids[-1]
    return {
        "type": "ready_to_advance",
        "message": (
            f"Ya dominas \"{titles.get(last_mastered, last_mastered)}\" — es buen momento para "
            f"comenzar \"{titles.get(next_course, next_course)}\"."
        ),
        "evidence": {"mastered_course_id": last_mastered, "next_course_id": next_course},
    }


def generate_insights(user_id: str, field_id: str, course_ids_in_order: list[str], titles: dict) -> list[dict]:
    insights: list[dict] = []
    insights.extend(_quiz_trend_insights(user_id, titles))
    mistake_insight = _mistake_concentration_insight(user_id, field_id, titles)
    if mistake_insight:
        insights.append(mistake_insight)
    mastery_insight = _mastery_transition_insight(user_id, field_id, course_ids_in_order, titles)
    if mastery_insight:
        insights.append(mastery_insight)
    return insights
