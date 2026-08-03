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


def test_grade_to_quality_dynamic_scaffolding_for_slow_correct_answers():
    # "Dynamic scaffolding": a correct answer that took unusually long
    # signals hesitation, not confident recall — it should still pass
    # (never drop to the "wrong" tier) but schedule sooner review than a
    # quick correct answer would, instead of every correct answer being
    # treated as equally mastered.
    fast = srs.grade_to_quality(correct=True, attempts_before_correct=0, response_ms=500)
    slow = srs.grade_to_quality(correct=True, attempts_before_correct=0, response_ms=15000)
    assert fast == 5
    assert slow == 3
    assert slow >= 3  # still a pass, never treated as an actual mistake

    # A wrong answer is graded the same regardless of how long it took —
    # slowness only matters as a signal on top of an otherwise-correct answer.
    assert srs.grade_to_quality(correct=False, response_ms=15000) == 1

    # response_ms=None (the default) means "not measured" — must not be
    # misread as "instant," which would otherwise trivially always pass
    # through as fast/confident.
    assert srs.grade_to_quality(correct=True, attempts_before_correct=0, response_ms=None) == 5


def test_slow_correct_answer_schedules_sooner_review_than_a_fast_one():
    _make_user()
    fast_schedule = srs.schedule_review("u1", "word.fast", quality=srs.grade_to_quality(True, 0, response_ms=500))
    slow_schedule = srs.schedule_review("u1", "word.slow", quality=srs.grade_to_quality(True, 0, response_ms=15000))
    assert slow_schedule["interval_days"] <= fast_schedule["interval_days"]
    assert slow_schedule["ease_factor"] < fast_schedule["ease_factor"]


def test_schedule_review_persists_content_snapshot():
    _make_user()
    srs.schedule_review("u1", "greetings.hello", quality=1, target_text="Hola", native_text="Hello", unit_id="A1-0")
    with db.cursor() as cur:
        cur.execute("SELECT target_text, native_text, unit_id FROM vocab_progress WHERE user_id='u1' AND vocab_key='greetings.hello'")
        row = cur.fetchone()
    assert row["target_text"] == "Hola"
    assert row["native_text"] == "Hello"
    assert row["unit_id"] == "A1-0"


def test_schedule_review_does_not_blank_content_snapshot_on_later_calls():
    # speak_repeat and similar call sites grade without a clean native_text
    # on hand — a later call with blank content must not erase what an
    # earlier call already captured.
    _make_user()
    srs.schedule_review("u1", "greetings.hello", quality=5, target_text="Hola", native_text="Hello", unit_id="A1-0")
    srs.schedule_review("u1", "greetings.hello", quality=5)
    with db.cursor() as cur:
        cur.execute("SELECT target_text, native_text FROM vocab_progress WHERE user_id='u1' AND vocab_key='greetings.hello'")
        row = cur.fetchone()
    assert row["target_text"] == "Hola"
    assert row["native_text"] == "Hello"


def test_due_review_items_returns_content_for_due_items_only():
    _make_user()
    # Due immediately: a failed review (interval 0.25 days is still in the past by now? no —
    # it's in the future by 6h). Force due_at into the past directly to simulate time passing.
    srs.schedule_review("u1", "due.word", quality=5, target_text="Perro", native_text="Dog", unit_id="A1-1")
    with db.cursor() as cur:
        cur.execute("UPDATE vocab_progress SET due_at = '2000-01-01T00:00:00+00:00' WHERE vocab_key='due.word'")
    srs.schedule_review("u1", "not_due.word", quality=5, target_text="Gato", native_text="Cat", unit_id="A1-1")

    items = srs.due_review_items("u1")
    keys = [i["vocab_key"] for i in items]
    assert "due.word" in keys
    assert "not_due.word" not in keys
    due_item = next(i for i in items if i["vocab_key"] == "due.word")
    assert due_item["target_text"] == "Perro"
    assert due_item["native_text"] == "Dog"
    assert due_item["unit_id"] == "A1-1"


def test_due_review_items_skips_rows_with_no_content_snapshot():
    # A vocab_key graded before this feature existed (or via a call site that
    # never passes content) has no target_text — nothing to review it with.
    _make_user()
    srs.schedule_review("u1", "legacy.word", quality=5)
    with db.cursor() as cur:
        cur.execute("UPDATE vocab_progress SET due_at = '2000-01-01T00:00:00+00:00' WHERE vocab_key='legacy.word'")
    assert srs.due_review_items("u1") == []


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


def test_record_lesson_result_levels_up_only_after_mastering_the_whole_level():
    # A genuine 0-to-native progression requires actually covering a CEFR
    # level's curriculum, not a small, level-size-independent fraction of
    # it — see srs.units_required_for_level_up.
    _make_user()
    from backend.curriculum import units_for_level

    unit_ids = [u.id for u in units_for_level(CEFRLevel.A1)]
    assert len(unit_ids) > 1  # otherwise this test wouldn't prove anything

    result = None
    for unit_id in unit_ids[:-1]:
        result = srs.record_lesson_result("u1", unit_id, score=1.0)
    assert result["leveled_up"] is None  # not yet — one unit still unmastered

    result = srs.record_lesson_result("u1", unit_ids[-1], score=1.0)
    assert result["leveled_up"] == CEFRLevel.A2.value


def test_units_required_for_level_up_scales_with_level_size():
    # Regression: the old flat constant (3) meant advancing past A1 (8
    # units) needed ~37% mastered while advancing past C2 (4 units) needed
    # 75% — an inconsistent bar purely because of level size, not because
    # C2 learners are held to a stricter standard on purpose.
    assert srs.units_required_for_level_up(8) == 8
    assert srs.units_required_for_level_up(4) == 4
    assert srs.units_required_for_level_up(0) == 1  # never zero — always at least 1


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
