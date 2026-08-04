"""The tutor's persistent memory of one student — the "perfil permanente"
from the request. Deliberately NOT a new store of tracked facts duplicating
what already exists elsewhere: every field here is either read straight
from data the rest of the learning engine (or the base app) already
tracks, or is the one genuinely new piece of state a student profile
needs that nothing else captures — their stated career_goal.

Field-by-field mapping back to the request's list:
- fortalezas/debilidades: competency.strengths_and_weaknesses
- errores frecuentes: academy_question_attempt, scoped to this student
- conceptos olvidados: concept_review.due_concepts — a concept becomes due
  again precisely because SM-2 predicts the student's retention of it has
  dropped; that prediction IS "forgotten," not a separate tracked fact
- velocidad de aprendizaje / tiempo promedio por sesión: this student's
  avg time per completed course vs. the field-wide average
  (learning_engine.analytics.field_summary)
- intereses: users.interests (already collected at onboarding)
- historial completo / cursos completados: learning_engine.portfolio
- objetivos: career_goal — the one new column this module adds
  (academy_enrollment.career_goal)
"""

from __future__ import annotations

from .. import db
from . import competency, concept_review


def set_career_goal(user_id: str, goal: str) -> None:
    with db.cursor() as cur:
        cur.execute("UPDATE academy_enrollment SET career_goal=? WHERE user_id=?", (goal.strip(), user_id))


def get_career_goal(user_id: str) -> str:
    with db.cursor() as cur:
        cur.execute("SELECT career_goal FROM academy_enrollment WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row["career_goal"] if row else ""


def frequent_mistakes(user_id: str, field_id: str, top_n: int = 5) -> list[dict]:
    """This student's own most-repeated wrong answers — distinct from
    analytics.field_summary's most_failed_questions, which aggregates
    across every student instead of one."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT course_id, question_text, COUNT(*) AS times_missed
            FROM academy_question_attempt
            WHERE user_id=? AND course_id LIKE ? AND correct=0
            GROUP BY course_id, question_text
            ORDER BY times_missed DESC
            LIMIT ?
            """,
            (user_id, f"{field_id}:%", top_n),
        )
        return [dict(r) for r in cur.fetchall()]


def learning_velocity(user_id: str, field_id: str) -> dict:
    """This student's average time per completed course vs. every other
    student's average in the same field — "más rápido", "más lento", or
    "promedio". None/None (relative="sin_datos") until they've completed
    at least one course."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT AVG(elapsed_seconds) AS avg_seconds FROM academy_course_progress "
            "WHERE user_id=? AND course_id LIKE ?",
            (user_id, f"{field_id}:%"),
        )
        user_row = cur.fetchone()
        cur.execute(
            "SELECT AVG(elapsed_seconds) AS avg_seconds FROM academy_course_progress WHERE course_id LIKE ?",
            (f"{field_id}:%",),
        )
        field_row = cur.fetchone()

    user_avg = user_row["avg_seconds"]
    field_avg = field_row["avg_seconds"]
    if user_avg is None or field_avg is None or field_avg == 0:
        relative = "sin_datos"
    elif user_avg < field_avg * 0.85:
        relative = "más_rápido"
    elif user_avg > field_avg * 1.15:
        relative = "más_lento"
    else:
        relative = "promedio"

    return {
        "user_avg_seconds": user_avg,
        "field_avg_seconds": field_avg,
        "relative": relative,
    }


def profile_summary(user_id: str, field_id: str, interests: list[str]) -> dict:
    return {
        "career_goal": get_career_goal(user_id),
        "interests": interests,
        "strengths_and_weaknesses": competency.strengths_and_weaknesses(user_id, field_id),
        "frequent_mistakes": frequent_mistakes(user_id, field_id),
        "forgotten_concepts": concept_review.due_concepts(user_id),
        "learning_velocity": learning_velocity(user_id, field_id),
    }
