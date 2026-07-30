from backend import db, srs
from backend.models import CEFRLevel


def _make_user(
    user_id="u1",
    level=CEFRLevel.A1,
    last_active_date="2000-01-01",
    streak_days=0,
    gems=0,
    streak_freezes=0,
):
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO users
               (id, display_name, native_lang, target_lang, level, interests, xp, streak_days,
                gems, streak_freezes, created_at, last_active_date)
               VALUES (?, 'Test', 'en', 'es', ?, '[]', 0, ?, ?, ?, ?, ?)""",
            (user_id, level.value, streak_days, gems, streak_freezes, db.now_iso(), last_active_date),
        )


def test_schedule_review_progresses_intervals_on_success():
    _make_user()
    first = srs.schedule_review("u1", "greetings.hello", quality=4)
    assert first["repetitions"] == 1
    assert first["interval_days"] == 1

    second = srs.schedule_review("u1", "greetings.hello", quality=4)
    assert second["repetitions"] == 2
    assert second["interval_days"] == 3

    third = srs.schedule_review("u1", "greetings.hello", quality=5)
    assert third["repetitions"] == 3
    assert third["interval_days"] > 3


def test_schedule_review_resets_on_failure():
    _make_user()
    srs.schedule_review("u1", "greetings.hello", quality=5)
    failed = srs.schedule_review("u1", "greetings.hello", quality=1)
    assert failed["repetitions"] == 0
    assert failed["interval_days"] == 0.25


def test_grade_to_quality():
    assert srs.grade_to_quality(correct=False) == 1
    assert srs.grade_to_quality(correct=True, attempts_before_correct=0) == 5
    assert srs.grade_to_quality(correct=True, attempts_before_correct=3) == 3


def test_recent_mistakes_orders_by_mistake_count():
    _make_user()
    srs.schedule_review("u1", "a.word", quality=1)
    srs.schedule_review("u1", "a.word", quality=1)
    srs.schedule_review("u1", "b.word", quality=1)
    mistakes = srs.recent_mistakes("u1")
    assert mistakes[0] == "a.word"


def test_record_lesson_result_awards_xp_and_streak():
    _make_user()
    result = srs.record_lesson_result("u1", "A1-0", score=1.0)
    assert result["xp_gained"] == 30
    assert result["streak_days"] == 1
    assert result["mastered"] is True


def test_record_lesson_result_levels_up_after_enough_mastered_units():
    _make_user()
    from backend.curriculum import units_for_level

    unit_ids = [u.id for u in units_for_level(CEFRLevel.A1)]
    result = None
    for unit_id in unit_ids[: srs.UNITS_TO_UNLOCK_NEXT_LEVEL]:
        result = srs.record_lesson_result("u1", unit_id, score=1.0)
    assert result["leveled_up"] == CEFRLevel.A2.value


def test_record_lesson_result_awards_gems():
    _make_user()
    result = srs.record_lesson_result("u1", "A1-0", score=1.0)
    assert result["gems_gained"] == 10  # GEM_BASE(5) + score(1.0)*5
    assert result["gems_total"] == 10


def test_streak_continues_normally_after_one_day_gap():
    from datetime import UTC, datetime, timedelta

    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    _make_user(last_active_date=yesterday, streak_days=4)
    result = srs.record_lesson_result("u1", "A1-0", score=1.0)
    assert result["streak_days"] == 5
    assert result["streak_freeze_used"] is False


def test_streak_freeze_auto_consumed_on_missed_day():
    from datetime import UTC, datetime, timedelta

    two_days_ago = (datetime.now(UTC).date() - timedelta(days=2)).isoformat()
    _make_user(last_active_date=two_days_ago, streak_days=4, streak_freezes=1)
    result = srs.record_lesson_result("u1", "A1-0", score=1.0)
    assert result["streak_days"] == 5  # protected, not reset
    assert result["streak_freeze_used"] is True
    assert result["streak_freezes_remaining"] == 0


def test_streak_resets_without_enough_freezes():
    from datetime import UTC, datetime, timedelta

    three_days_ago = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    _make_user(last_active_date=three_days_ago, streak_days=10, streak_freezes=1)
    result = srs.record_lesson_result("u1", "A1-0", score=1.0)
    # gap of 3 days needs 2 freezes; only 1 banked -> streak resets
    assert result["streak_days"] == 1
    assert result["streak_freeze_used"] is False


def test_buy_streak_freeze_deducts_gems():
    _make_user(gems=250)
    result = srs.buy_streak_freeze("u1")
    assert result["gems"] == 50
    assert result["streak_freezes"] == 1


def test_buy_streak_freeze_fails_without_enough_gems():
    _make_user(gems=50)
    try:
        srs.buy_streak_freeze("u1")
        assert False, "expected ShopError"
    except srs.ShopError:
        pass


def test_today_practice_minutes_sums_elapsed_seconds_for_today():
    _make_user()
    srs.record_lesson_result("u1", "A1-0", score=1.0, elapsed_seconds=90)
    srs.record_lesson_result("u1", "A1-1", score=1.0, elapsed_seconds=150)
    assert srs.today_practice_minutes("u1") == 4  # (90+150)/60 = 4


def test_weekly_leaderboard_ranks_by_xp_and_marks_you():
    _make_user("u1")
    _make_user("u2")
    srs.record_lesson_result("u1", "A1-0", score=1.0)
    srs.record_lesson_result("u2", "A1-0", score=1.0)
    srs.record_lesson_result("u2", "A1-1", score=1.0)

    entries, your_xp, your_rank = srs.get_weekly_leaderboard("u1")
    assert entries[0]["display_name"] == "Test"
    assert entries[0]["weekly_xp"] == 60  # u2 earned two lessons worth
    assert entries[0]["is_you"] is False
    assert your_xp == 30
    assert your_rank == 2


def test_weekly_leaderboard_rank_present_outside_top_limit():
    _make_user("u1")
    _make_user("u2")
    srs.record_lesson_result("u2", "A1-0", score=1.0)
    srs.record_lesson_result("u1", "A1-0", score=1.0)

    entries, _, your_rank = srs.get_weekly_leaderboard("u1", limit=1)
    assert len(entries) == 1
    assert your_rank == 2  # u1 exists even though only the top 1 is returned
