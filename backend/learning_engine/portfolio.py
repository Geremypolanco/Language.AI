"""Automatic professional portfolio: aggregates real evidence of a
student's work — submitted assignments, resolved practice scenarios, and
completed courses — into one view. Deliberately not its own tracked state:
every item here was already earned through real graded/submitted work
recorded elsewhere (academy_assignment_submission, academy_scenario_
submission, academy_course_progress); this module only collects it.

Scoped across every field the student has ever studied, not just their
current enrollment — academy_enrollment only remembers the CURRENT field
(re-enrolling overwrites it), but submissions from an earlier field are
never deleted, so a real portfolio should show all of it, not just what's
active right now.
"""

from __future__ import annotations

from .. import db


def get_portfolio(user_id: str) -> dict:
    with db.cursor() as cur:
        cur.execute(
            "SELECT course_id, assignment_id, response, feedback, grade, submitted_at "
            "FROM academy_assignment_submission WHERE user_id=? ORDER BY submitted_at DESC",
            (user_id,),
        )
        assignments = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT course_id, scenario, response, feedback, submitted_at "
            "FROM academy_scenario_submission WHERE user_id=? ORDER BY submitted_at DESC",
            (user_id,),
        )
        scenarios = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT course_id, completed_at, elapsed_seconds FROM academy_course_progress "
            "WHERE user_id=? ORDER BY completed_at DESC",
            (user_id,),
        )
        completed_courses = [dict(r) for r in cur.fetchall()]

    return {
        "assignments": assignments,
        "scenarios": scenarios,
        "completed_courses": completed_courses,
    }
