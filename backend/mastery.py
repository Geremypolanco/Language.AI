"""Real, DB-backed academic mastery tracking for faculty-persona Q&A turns.

Scope note — read before extending this: the request that produced this file
asked for an engine that auto-skips "the remaining Associate/Bachelor modules"
and hot-swaps a student straight into Master/PhD-level material after 3
conversational turns scoring above a threshold. This module deliberately does
NOT do that, for two concrete reasons:

1. `academic_depth_score` is an LLM's own real-time self-assessment of the
   conversation it's currently having, with no external calibration or
   ground truth — treating 3 samples of it as sufficient evidence to grant
   the equivalent of ~2 dozen courses' worth of credit would be building a
   fabricated-legitimacy mechanic, not a grading system.
2. backend/academy.py's own module docstring is explicit that this app
   "issues no real degree, credit, or certificate" — silently jumping degree
   levels contradicts that disclaimer instead of honoring it.

What IS real and defensible: a sustained streak of strong turns on ONE
specific course is reasonable evidence that the student has mastered THAT
course's material, so it's marked complete early. Only after every course at
the student's current level is actually completed does this module surface a
(non-mutating) recommendation to consider enrolling at the next level — the
existing /api/academy/{user_id}/enroll endpoint still requires an explicit
student action to act on it.
"""

from __future__ import annotations

from typing import Any

from . import db
from .models import AcademicLevel

# Consecutive faculty-graded turns, on the SAME course, required before a
# mastery streak fast-tracks that course's completion.
MASTERY_STREAK_LENGTH = 3
# academic_depth_score is documented (see curriculum.py's ACADEMIC GRADING
# block) as a 1-100 int; 93+ across an entire streak with zero logged
# fallacies is a deliberately high bar, not a routine pass mark.
MASTERY_DEPTH_THRESHOLD = 93

_LEVEL_SEQUENCE = [AcademicLevel.ASSOCIATE, AcademicLevel.BACHELOR, AcademicLevel.MASTER, AcademicLevel.DOCTORATE]


def _next_level(level: AcademicLevel) -> AcademicLevel | None:
    idx = _LEVEL_SEQUENCE.index(level)
    return _LEVEL_SEQUENCE[idx + 1] if idx + 1 < len(_LEVEL_SEQUENCE) else None


def _parse_course_id(course_id: str) -> tuple[str, AcademicLevel, int]:
    """course_id is always `{field_id}:{level.value}:{order}` — see
    routers/academy.py's _course_id(). Field ids and AcademicLevel values are
    fixed slugs/enum names with no colons in them, so a plain split is exact."""
    field_id, level_value, order_str = course_id.split(":")
    return field_id, AcademicLevel(level_value), int(order_str)


def evaluate_academic_promotion(user_id: str, course_id: str, critique_metrics: dict[str, Any]) -> dict[str, Any]:
    """Logs one faculty-graded turn and, on a genuine mastery streak for this
    course, marks it complete early. Returns a result describing what
    happened — never raises for a mastery-less turn, only for a malformed
    course_id (a caller bug, not a runtime condition to swallow)."""
    field_id, level, _order = _parse_course_id(course_id)

    depth_score = critique_metrics.get("academic_depth_score")
    fallacy_count = len(critique_metrics.get("structural_logical_fallacies") or [])

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_mastery_log (user_id, course_id, academic_depth_score, fallacy_count, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, course_id, depth_score, fallacy_count, db.now_iso()),
        )
        cur.execute(
            "SELECT academic_depth_score, fallacy_count FROM academy_mastery_log "
            "WHERE user_id=? AND course_id=? ORDER BY id DESC LIMIT ?",
            (user_id, course_id, MASTERY_STREAK_LENGTH),
        )
        recent = cur.fetchall()

    streak_achieved = (
        len(recent) == MASTERY_STREAK_LENGTH
        and all(
            r["academic_depth_score"] is not None and r["academic_depth_score"] >= MASTERY_DEPTH_THRESHOLD
            for r in recent
        )
        and all(r["fallacy_count"] == 0 for r in recent)
    )

    result: dict[str, Any] = {
        "course_id": course_id,
        "streak_length": len(recent),
        "course_fast_tracked": False,
        "level_complete_recommendation": False,
        "recommended_next_level": None,
    }
    if not streak_achieved:
        return result

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, course_id) DO NOTHING",
            (user_id, course_id, db.now_iso()),
        )
        cur.execute("SELECT course_id FROM academy_course_progress WHERE user_id=?", (user_id,))
        completed = {r["course_id"] for r in cur.fetchall()}

    result["course_fast_tracked"] = True

    prefix = f"{field_id}:{level.value}:"
    completed_at_this_level = sum(1 for cid in completed if cid.startswith(prefix))
    if completed_at_this_level >= level.course_count:
        next_level = _next_level(level)
        result["level_complete_recommendation"] = next_level is not None
        result["recommended_next_level"] = next_level.value if next_level else None

    return result
