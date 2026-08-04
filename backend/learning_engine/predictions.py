"""Honest, transparent heuristics — explicitly NOT machine learning.

This app has no labeled outcome data (no historical "did this student
actually pass or drop out" dataset) and no training pipeline, so there is
nothing to fit or validate a real predictive model against. Every
function here computes a plain, inspectable number from data the
platform already tracks, and documents exactly how — so "riesgo: alto"
always traces back to a fact the student could look up themselves (days
since their last activity, items overdue for review, their own past
completion rate). None of this is a fabricated "87% probability of
passing" — that phrasing implies a statistical model that was never
built or validated, and this module deliberately never produces it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from .. import db, srs


def forgetting_risk(user_id: str) -> dict:
    """Reuses the existing SM-2 due-item logic (backend/srs.py) instead of
    a second retention model — an item becoming "due" already IS the
    system's existing prediction that recall has decayed. This just
    summarizes how many items are due and how overdue the oldest one is.
    Spans both language vocabulary and academic concepts, since both share
    vocab_progress (see srs.due_review_items's key_prefix docstring)."""
    due_count = srs.due_review_count(user_id)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM vocab_progress WHERE user_id=?", (user_id,))
        total = cur.fetchone()["c"]
        cur.execute(
            "SELECT MIN(due_at) AS oldest FROM vocab_progress WHERE user_id=? AND due_at<=?",
            (user_id, datetime.now(UTC).isoformat()),
        )
        oldest = cur.fetchone()["oldest"]

    overdue_days = 0
    if oldest:
        overdue_days = max(0, (datetime.now(UTC) - datetime.fromisoformat(oldest)).days)

    if total == 0:
        level = "sin_datos"
    elif due_count == 0:
        level = "bajo"
    elif due_count / total < 0.3 and overdue_days < 3:
        level = "medio"
    else:
        level = "alto"

    return {"due_count": due_count, "tracked_total": total, "overdue_days_max": overdue_days, "risk_level": level}


def dropout_risk(user_id: str) -> dict:
    """From days-since-last-active vs. the student's own streak — both
    already tracked on `users` (see srs.record_lesson_result), not a new
    signal. A broken streak (streak_days reset to 0) on top of a gap is a
    stronger signal than the same gap alone, since it means this student
    specifically had built a habit and lost it, not just a naturally
    slower pace."""
    with db.cursor() as cur:
        cur.execute("SELECT last_active_date, streak_days FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()

    if row is None or not row["last_active_date"]:
        return {"days_since_last_active": None, "streak_days": 0, "risk_level": "sin_datos"}

    today = date.fromisoformat(db.today_str())
    days_since = (today - date.fromisoformat(row["last_active_date"])).days
    streak = row["streak_days"]

    if days_since <= 1:
        level = "bajo"
    elif days_since <= 3:
        level = "medio"
    else:
        level = "alto"
    if streak == 0 and days_since >= 2:
        level = "alto"

    return {"days_since_last_active": days_since, "streak_days": streak, "risk_level": level}


def time_to_mastery_estimate(enrolled_at: str, completed_count: int, total_courses: int) -> dict:
    """Linear extrapolation of the student's own historical completion
    rate — not a model, just "at the pace you've kept up so far, this is
    how long the rest would take at that same pace." Returns
    estimated_days_remaining=None when there isn't enough history yet to
    extrapolate from (zero courses completed), rather than guessing."""
    remaining = max(0, total_courses - completed_count)
    if remaining == 0:
        return {"remaining_courses": 0, "estimated_days_remaining": 0, "pace_courses_per_day": None}
    if completed_count == 0:
        return {"remaining_courses": remaining, "estimated_days_remaining": None, "pace_courses_per_day": None}

    enrolled_date = datetime.fromisoformat(enrolled_at).date()
    elapsed_days = max(1, (date.fromisoformat(db.today_str()) - enrolled_date).days)
    pace = completed_count / elapsed_days
    estimated_days = round(remaining / pace) if pace > 0 else None

    return {
        "remaining_courses": remaining,
        "estimated_days_remaining": estimated_days,
        "pace_courses_per_day": round(pace, 4),
    }
