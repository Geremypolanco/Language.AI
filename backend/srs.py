"""Adaptive spaced-repetition scheduling (SM-2 family) and unit-mastery/leveling
logic — the core of "adapts to the user" instead of a fixed static course.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from . import db
from .models import CEFRLevel

MASTERY_SCORE_THRESHOLD = 0.8  # avg correctness required to consider a unit mastered
UNITS_TO_UNLOCK_NEXT_LEVEL = 3  # mastered units at current level before leveling up

GEM_BASE = 5  # gems per completed lesson, plus a score-scaled bonus below
GEM_STREAK_FREEZE_COST = 200


class ShopError(Exception):
    """Raised when a gem purchase can't go through (not enough gems, etc)."""


# A correct answer that took longer than this to give is graded as
# hesitant rather than confident recall — "dynamic scaffolding": schedule
# it for sooner review (see schedule_review's quality->ease formula) even
# though it was technically right, instead of treating every correct
# answer as equally mastered regardless of how long it took. Deliberately
# crude (a fixed threshold, not adapted per exercise type or learner) —
# good enough to catch "answered right but clearly had to think hard about
# it" without needing per-user response-time baselines.
_SLOW_RESPONSE_MS = 8000


def grade_to_quality(correct: bool, attempts_before_correct: int = 0, response_ms: int | None = None) -> int:
    """Maps a boolean result to an SM-2 quality score (0-5)."""
    if not correct:
        return 1
    quality = max(3, 5 - attempts_before_correct)
    if response_ms is not None and response_ms > _SLOW_RESPONSE_MS:
        # Still passes (never below 3 — it WAS correct), but caps at the
        # "needs more practice" tier instead of a full-confidence 5.
        quality = min(quality, 3)
    return quality


def schedule_review(user_id: str, vocab_key: str, quality: int) -> dict:
    """SM-2 update for a single vocabulary item. Returns the new schedule row."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT ease_factor, interval_days, repetitions, mistake_count "
            "FROM vocab_progress WHERE user_id=? AND vocab_key=?",
            (user_id, vocab_key),
        )
        row = cur.fetchone()
        ease = row["ease_factor"] if row else 2.5
        interval = row["interval_days"] if row else 0.0
        reps = row["repetitions"] if row else 0
        mistakes = row["mistake_count"] if row else 0

        if quality < 3:
            reps = 0
            interval = 0.25  # revisit within the same/next session (~6h)
            mistakes += 1
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = round(interval * ease, 2)
            reps += 1

        ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        due_at = (datetime.now(UTC) + timedelta(days=interval)).isoformat()

        cur.execute(
            """
            INSERT INTO vocab_progress
                (user_id, vocab_key, ease_factor, interval_days, repetitions, due_at, last_result, mistake_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, vocab_key) DO UPDATE SET
                ease_factor=excluded.ease_factor,
                interval_days=excluded.interval_days,
                repetitions=excluded.repetitions,
                due_at=excluded.due_at,
                last_result=excluded.last_result,
                mistake_count=excluded.mistake_count
            """,
            (user_id, vocab_key, ease, interval, reps, due_at, "correct" if quality >= 3 else "incorrect", mistakes),
        )
        return {
            "vocab_key": vocab_key,
            "ease_factor": ease,
            "interval_days": interval,
            "repetitions": reps,
            "due_at": due_at,
        }


def due_review_keys(user_id: str, limit: int = 10) -> list[str]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT vocab_key FROM vocab_progress WHERE user_id=? AND due_at<=? "
            "ORDER BY due_at ASC LIMIT ?",
            (user_id, datetime.now(UTC).isoformat(), limit),
        )
        return [r["vocab_key"] for r in cur.fetchall()]


def due_review_count(user_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM vocab_progress WHERE user_id=? AND due_at<=?",
            (user_id, datetime.now(UTC).isoformat()),
        )
        return cur.fetchone()["c"]


def recent_mistakes(user_id: str, limit: int = 5) -> list[str]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT vocab_key FROM vocab_progress WHERE user_id=? AND mistake_count>0 "
            "ORDER BY mistake_count DESC, due_at ASC LIMIT ?",
            (user_id, limit),
        )
        return [r["vocab_key"] for r in cur.fetchall()]


def record_lesson_result(user_id: str, unit_id: str, score: float, elapsed_seconds: int = 0) -> dict:
    """Records a completed lesson, updates mastery, and awards XP/streak/gems.
    Returns a summary the API can hand straight back to the client."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO lesson_history (user_id, unit_id, score, completed_at, elapsed_seconds) VALUES (?,?,?,?,?)",
            (user_id, unit_id, score, db.now_iso(), max(0, elapsed_seconds)),
        )
        cur.execute(
            "SELECT best_score, attempts FROM unit_mastery WHERE user_id=? AND unit_id=?",
            (user_id, unit_id),
        )
        row = cur.fetchone()
        best = max(score, row["best_score"]) if row else score
        attempts = (row["attempts"] if row else 0) + 1
        mastered = 1 if best >= MASTERY_SCORE_THRESHOLD else 0
        cur.execute(
            """
            INSERT INTO unit_mastery (user_id, unit_id, best_score, attempts, mastered)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, unit_id) DO UPDATE SET
                best_score=excluded.best_score, attempts=excluded.attempts, mastered=excluded.mastered
            """,
            (user_id, unit_id, best, attempts, mastered),
        )

        xp_gain = round(10 + score * 20)
        gems_gain = round(GEM_BASE + score * 5)
        cur.execute(
            "SELECT xp, streak_days, gems, streak_freezes, last_active_date, level FROM users WHERE id=?",
            (user_id,),
        )
        u = cur.fetchone()
        new_xp = u["xp"] + xp_gain
        new_gems = u["gems"] + gems_gain
        today_str = db.today_str()
        today = date.fromisoformat(today_str)
        streak = u["streak_days"]
        freezes = u["streak_freezes"]
        streak_freeze_used = False

        if u["last_active_date"] != today_str:
            if not u["last_active_date"]:
                streak = 1  # first-ever activity
            else:
                gap_days = (today - date.fromisoformat(u["last_active_date"])).days
                if gap_days == 1:
                    streak += 1
                else:
                    # Missed (gap_days - 1) full calendar days — Duolingo-style streak
                    # freezes auto-consume one per missed day if you have enough banked.
                    freezes_needed = gap_days - 1
                    if freezes >= freezes_needed:
                        freezes -= freezes_needed
                        streak += 1
                        streak_freeze_used = True
                    else:
                        streak = 1

        cur.execute(
            "UPDATE users SET xp=?, streak_days=?, last_active_date=?, gems=?, streak_freezes=? WHERE id=?",
            (new_xp, streak, today_str, new_gems, freezes, user_id),
        )

        leveled_up = _maybe_level_up(cur, user_id, CEFRLevel(u["level"]))

        return {
            "xp_gained": xp_gain,
            "xp_total": new_xp,
            "gems_gained": gems_gain,
            "gems_total": new_gems,
            "streak_days": streak,
            "streak_freeze_used": streak_freeze_used,
            "streak_freezes_remaining": freezes,
            "mastered": bool(mastered),
            "leveled_up": leveled_up,
        }


def _maybe_level_up(cur, user_id: str, current_level: CEFRLevel) -> str | None:
    from .curriculum import units_for_level

    unit_ids = [u.id for u in units_for_level(current_level)]
    if not unit_ids:
        return None
    placeholders = ",".join("?" for _ in unit_ids)
    cur.execute(
        f"SELECT COUNT(*) AS c FROM unit_mastery WHERE user_id=? AND mastered=1 AND unit_id IN ({placeholders})",
        (user_id, *unit_ids),
    )
    mastered_count = cur.fetchone()["c"]
    if mastered_count >= min(UNITS_TO_UNLOCK_NEXT_LEVEL, len(unit_ids)):
        next_level = current_level.next
        if next_level != current_level:
            cur.execute("UPDATE users SET level=? WHERE id=?", (next_level.value, user_id))
            return next_level.value
    return None


# ── Gem shop ──────────────────────────────────────────────────────────────


def buy_streak_freeze(user_id: str) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT gems, streak_freezes FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        if row["gems"] < GEM_STREAK_FREEZE_COST:
            raise ShopError("No tienes suficientes gemas para una congelación de racha")
        new_gems = row["gems"] - GEM_STREAK_FREEZE_COST
        new_freezes = row["streak_freezes"] + 1
        cur.execute("UPDATE users SET gems=?, streak_freezes=? WHERE id=?", (new_gems, new_freezes, user_id))
        return {"gems": new_gems, "streak_freezes": new_freezes}


# ── Practice time (self-chosen daily goal, never an enforced cap) ──────────


def today_practice_minutes(user_id: str) -> int:
    today = db.today_str()
    with db.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(elapsed_seconds), 0) AS total FROM lesson_history "
            "WHERE user_id=? AND completed_at LIKE ?",
            (user_id, f"{today}%"),
        )
        return round(cur.fetchone()["total"] / 60)


# ── Weekly leaderboard ──────────────────────────────────────────────────────


def get_weekly_leaderboard(user_id: str, limit: int = 10) -> tuple[list[dict], int, int | None]:
    """Ranks every user by XP earned since this Monday (recomputed from
    lesson_history's own scores — no separate weekly-XP column to keep in
    sync). Returns (top `limit` entries, the requester's own weekly XP, the
    requester's own rank — present even when they're outside the top N)."""
    today = datetime.now(UTC).date()
    monday = (today - timedelta(days=today.weekday())).isoformat()

    with db.cursor() as cur:
        cur.execute("SELECT user_id, score FROM lesson_history WHERE completed_at >= ?", (monday,))
        rows = cur.fetchall()

    xp_by_user: dict[str, int] = {}
    for r in rows:
        xp_by_user[r["user_id"]] = xp_by_user.get(r["user_id"], 0) + round(10 + r["score"] * 20)

    your_weekly_xp = xp_by_user.get(user_id, 0)
    if not xp_by_user:
        return [], 0, None

    user_ids = list(xp_by_user.keys())
    with db.cursor() as cur:
        placeholders = ",".join("?" for _ in user_ids)
        cur.execute(f"SELECT id, display_name FROM users WHERE id IN ({placeholders})", tuple(user_ids))
        names = {r["id"]: r["display_name"] for r in cur.fetchall()}

    ranked = sorted(xp_by_user.items(), key=lambda kv: kv[1], reverse=True)
    entries = []
    your_rank = None
    for i, (uid, xp) in enumerate(ranked):
        rank = i + 1
        if uid == user_id:
            your_rank = rank
        if rank <= limit:
            entries.append(
                {"rank": rank, "display_name": names.get(uid, "Learner"), "weekly_xp": xp, "is_you": uid == user_id}
            )
    return entries, your_weekly_xp, your_rank
