"""Progress data: the simple snapshot used in the top bar, and the richer
dashboard payload (mastery-by-level breakdown, activity history, recent
lessons) that drives the Progress tab's charts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from .. import auth, db, srs
from ..curriculum import get_unit, units_for_level
from ..models import (
    ActivityDay,
    CEFRLevel,
    DashboardData,
    LeaderboardEntry,
    LevelMastery,
    ProgressSnapshot,
    RecentLesson,
)
from .users import get_user_by_id_or_404

router = APIRouter(prefix="/api/progress", tags=["progress"])

_ACTIVITY_DAYS = 14


@router.get("/{user_id}", response_model=ProgressSnapshot)
def get_progress(user_id: str, session: dict = Depends(auth.require_owner)) -> ProgressSnapshot:
    user = get_user_by_id_or_404(user_id)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM unit_mastery WHERE user_id=? AND mastered=1", (user_id,))
        mastered = cur.fetchone()["c"]
    return ProgressSnapshot(
        user_id=user_id,
        xp=user.xp,
        streak_days=user.streak_days,
        gems=user.gems,
        streak_freezes=user.streak_freezes,
        level=user.level,
        due_reviews=srs.due_review_count(user_id),
        units_mastered=mastered,
        daily_goal_minutes=user.daily_goal_minutes,
        today_minutes=srs.today_practice_minutes(user_id),
    )


@router.get("/{user_id}/dashboard", response_model=DashboardData)
def get_dashboard(user_id: str, session: dict = Depends(auth.require_owner)) -> DashboardData:
    user = get_user_by_id_or_404(user_id)

    with db.cursor() as cur:
        cur.execute("SELECT unit_id FROM unit_mastery WHERE user_id=? AND mastered=1", (user_id,))
        mastered_ids = {row["unit_id"] for row in cur.fetchall()}

    mastery_by_level: list[LevelMastery] = []
    for level in CEFRLevel:
        units = units_for_level(level)
        if not units:
            continue
        mastered_count = sum(1 for u in units if u.id in mastered_ids)
        mastery_by_level.append(LevelMastery(level=level, mastered=mastered_count, total=len(units)))

    current = next((m for m in mastery_by_level if m.level == user.level), None)
    units_mastered_current = current.mastered if current else 0
    units_total_current = current.total if current else 0
    next_level = user.level.next if user.level.next != user.level else None

    cutoff = (datetime.now(UTC) - timedelta(days=_ACTIVITY_DAYS)).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "SELECT completed_at FROM lesson_history WHERE user_id=? AND completed_at>=?",
            (user_id, cutoff),
        )
        completed_dates = [row["completed_at"][:10] for row in cur.fetchall()]

    counts_by_day: dict[str, int] = {}
    for date_str in completed_dates:
        counts_by_day[date_str] = counts_by_day.get(date_str, 0) + 1

    today = datetime.now(UTC).date()
    activity = [
        ActivityDay(
            date=(today - timedelta(days=offset)).isoformat(),
            lessons_completed=counts_by_day.get((today - timedelta(days=offset)).isoformat(), 0),
        )
        for offset in range(_ACTIVITY_DAYS - 1, -1, -1)
    ]

    with db.cursor() as cur:
        cur.execute(
            "SELECT unit_id, score, completed_at FROM lesson_history WHERE user_id=? ORDER BY id DESC LIMIT 8",
            (user_id,),
        )
        recent_rows = cur.fetchall()

    recent_lessons = []
    for row in recent_rows:
        unit = get_unit(row["unit_id"])
        recent_lessons.append(
            RecentLesson(
                unit_id=row["unit_id"],
                topic=unit.topic if unit else row["unit_id"],
                score=row["score"],
                completed_at=row["completed_at"],
            )
        )

    leaderboard_rows, your_weekly_xp, your_rank = srs.get_weekly_leaderboard(user_id)
    leaderboard = [LeaderboardEntry(**row) for row in leaderboard_rows]

    return DashboardData(
        user_id=user_id,
        xp=user.xp,
        streak_days=user.streak_days,
        gems=user.gems,
        streak_freezes=user.streak_freezes,
        level=user.level,
        next_level=next_level,
        due_reviews=srs.due_review_count(user_id),
        units_mastered_current_level=units_mastered_current,
        units_total_current_level=units_total_current,
        units_required_for_next_level=min(srs.UNITS_TO_UNLOCK_NEXT_LEVEL, units_total_current or 1),
        daily_goal_minutes=user.daily_goal_minutes,
        today_minutes=srs.today_practice_minutes(user_id),
        mastery_by_level=mastery_by_level,
        activity=activity,
        recent_lessons=recent_lessons,
        leaderboard=leaderboard,
        your_weekly_xp=your_weekly_xp,
        your_rank=your_rank,
    )
