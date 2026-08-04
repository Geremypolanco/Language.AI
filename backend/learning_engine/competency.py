"""Competency tracking: replaces "percent of the course completed" with a
real mastery score per course, updated every time a student's quiz/exam
answers are graded (see grading.py).

Deliberately one competency per COURSE, not a separate named-skill
taxonomy ("Programming 92%, Algorithms 74%, Statistics 58%..."). Building
that taxonomy for real means deciding, for every one of ~60 fields, which
skills exist and which courses/concepts roll up into each one — content
design work, not architecture, and faking a plausible-looking taxonomy
without grounding it in real course content would be exactly the kind of
"looks complete, isn't real" result this app has consistently avoided.
A course's own subject is already a meaningful, real competency name
("Estructuras de Datos: 74%"); layering a broader taxonomy on top later
is additive (aggregate several course scores under one label) — not a
rewrite of what's built here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .. import db

MASTERY_THRESHOLD = 0.8

# Weight given to the newest quiz/exam result vs. the running average —
# same shape of idea as SM-2's ease factor in srs.py: a recent result should
# actually move the score, but one bad day (or one lucky guess) shouldn't
# overwrite an otherwise-established track record.
_EMA_ALPHA = 0.4


def record_result(user_id: str, field_id: str, course_id: str, score: float) -> float:
    """`score` is 0..1 — the fraction of a quiz/exam a student answered
    correctly (see grading.grade_submission). Returns the course's new
    competency score."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT score, attempts FROM academy_competency WHERE user_id=? AND course_id=?",
            (user_id, course_id),
        )
        row = cur.fetchone()
        if row is None:
            new_score = score
            attempts = 1
        else:
            new_score = row["score"] + _EMA_ALPHA * (score - row["score"])
            attempts = row["attempts"] + 1

        cur.execute(
            """
            INSERT INTO academy_competency (user_id, course_id, field_id, score, attempts, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, course_id) DO UPDATE SET
                score=excluded.score, attempts=excluded.attempts,
                updated_at=excluded.updated_at, field_id=excluded.field_id
            """,
            (user_id, course_id, field_id, new_score, attempts, datetime.now(UTC).isoformat()),
        )
        return new_score


def get_competencies(user_id: str, field_id: str | None = None) -> list[dict]:
    with db.cursor() as cur:
        if field_id:
            cur.execute(
                "SELECT course_id, field_id, score, attempts FROM academy_competency "
                "WHERE user_id=? AND field_id=? ORDER BY score DESC",
                (user_id, field_id),
            )
        else:
            cur.execute(
                "SELECT course_id, field_id, score, attempts FROM academy_competency "
                "WHERE user_id=? ORDER BY score DESC",
                (user_id,),
            )
        return [dict(row) for row in cur.fetchall()]


def get_competency(user_id: str, course_id: str) -> dict | None:
    with db.cursor() as cur:
        cur.execute(
            "SELECT course_id, field_id, score, attempts FROM academy_competency WHERE user_id=? AND course_id=?",
            (user_id, course_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def is_mastered(user_id: str, course_id: str) -> bool:
    comp = get_competency(user_id, course_id)
    return comp is not None and comp["score"] >= MASTERY_THRESHOLD


def strengths_and_weaknesses(user_id: str, field_id: str, top_n: int = 3) -> dict:
    """The two ends of a student's competency spread for a field — the
    "fortalezas/debilidades" the request asks the tutor profile to track.
    Courses never attempted (no competency row yet) aren't weaknesses,
    they're just unstarted — only attempted courses are ranked."""
    ranked = get_competencies(user_id, field_id)
    return {
        "strengths": ranked[:top_n],
        "weaknesses": list(reversed(ranked[-top_n:])) if ranked else [],
    }
