"""Analytics: read-only aggregations over data the rest of the learning
engine already tracks — no new tracked state of its own, just queries.

Two audiences, two functions:
- student_summary(): the "para estudiantes" half of the request — progress,
  time, competencies, strengths/weaknesses, recommendation. Mostly gluing
  together competency.py + recommendations.py, plus real elapsed-time data
  now that academy_course_progress tracks it (see routers/academy.py's
  CompleteCourseRequest).
- field_summary(): the "para administradores" half — aggregated across
  every student in one field, from academy_question_attempt (added
  specifically to make "preguntas más falladas" answerable) and
  academy_competency/academy_course_progress.

field_summary()'s "abandono" numbers are honestly scoped: there is no
"started this course" event tracked anywhere in the app today, only
"completed" — so this reports completion counts per course, not a true
enrolled-vs-abandoned ratio. Adding a real abandonment metric needs a
"course opened" event first, which is a small, separate addition on top of
this same table, not a redesign.
"""

from __future__ import annotations

from .. import db
from . import competency, recommendations


def student_summary(
    user_id: str, field_id: str, course_ids_in_order: list[str], course_titles: dict[str, str]
) -> dict:
    scores = competency.get_competencies(user_id, field_id)
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(elapsed_seconds), 0) AS total_seconds "
            "FROM academy_course_progress WHERE user_id=? AND course_id LIKE ?",
            (user_id, f"{field_id}:%"),
        )
        row = cur.fetchone()

    next_course = recommendations.recommend_next_course(user_id, field_id, course_ids_in_order)
    weak = recommendations.courses_needing_review(user_id, field_id, course_ids_in_order)

    return {
        "competencies": [{**c, "title": course_titles.get(c["course_id"], c["course_id"])} for c in scores],
        "strengths_and_weaknesses": competency.strengths_and_weaknesses(user_id, field_id),
        "courses_completed": row["n"],
        "total_time_minutes": round(row["total_seconds"] / 60),
        "next_course_id": next_course,
        "next_course_title": course_titles.get(next_course) if next_course else None,
        "courses_needing_review": [{"course_id": cid, "title": course_titles.get(cid, cid)} for cid in weak],
    }


def field_summary(field_id: str, top_n: int = 10) -> dict:
    prefix = f"{field_id}:%"
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT course_id, question_index, question_text,
                   SUM(CASE WHEN correct=0 THEN 1 ELSE 0 END) AS failures,
                   COUNT(*) AS attempts
            FROM academy_question_attempt
            WHERE course_id LIKE ?
            GROUP BY course_id, question_index, question_text
            ORDER BY failures DESC
            LIMIT ?
            """,
            (prefix, top_n),
        )
        most_failed = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT course_id, AVG(score) AS avg_score, COUNT(*) AS student_count "
            "FROM academy_competency WHERE field_id=? GROUP BY course_id ORDER BY avg_score ASC",
            (field_id,),
        )
        competency_by_course = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT course_id, COUNT(*) AS completions, AVG(elapsed_seconds) AS avg_seconds "
            "FROM academy_course_progress WHERE course_id LIKE ? GROUP BY course_id",
            (prefix,),
        )
        completions_by_course = [dict(r) for r in cur.fetchall()]

    return {
        "most_failed_questions": most_failed,
        "avg_competency_by_course": competency_by_course,
        "completions_by_course": completions_by_course,
    }
