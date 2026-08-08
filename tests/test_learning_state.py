from backend import db
from backend.learning_engine import competency
from backend.learning_engine.adaptation import for_conversation
from backend.learning_engine.learning_state import (
    STATE_VERSION,
    LearningStateProvider,
    build_learning_state,
)
from backend.learning_engine.student_profile import get_enrolled_field_id, set_career_goal


def _make_user(user_id="u1"):
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO users
               (id, display_name, native_lang, target_lang, level, interests, xp, streak_days,
                gems, streak_freezes, created_at, last_active_date)
               VALUES (?, 'Test', 'en', 'es', 'A1', '[]', 0, 0, 0, 0, ?, ?)""",
            (user_id, db.now_iso(), db.today_str()),
        )


def _make_enrollment(user_id="u1", field_id="f", level="BACHELOR"):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at, content_lang) VALUES (?, ?, ?, ?, 'es')",
            (user_id, field_id, level, db.now_iso()),
        )


def _record_mistake(user_id, field_id, question_text, times=1):
    with db.cursor() as cur:
        for _ in range(times):
            cur.execute(
                "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES (?, ?, 'quiz', 0, ?, 0, ?)",
                (user_id, f"{field_id}:BACHELOR:0", question_text, db.now_iso()),
            )


def test_get_enrolled_field_id_none_without_enrollment():
    _make_user()
    assert get_enrolled_field_id("u1") is None


def test_get_enrolled_field_id_returns_field():
    _make_user()
    _make_enrollment(field_id="software-engineering")
    assert get_enrolled_field_id("u1") == "software-engineering"


# ── LearningState ────────────────────────────────────────────────────────


def test_build_learning_state_traceable_fields_default_to_empty_without_data():
    _make_user()
    state = build_learning_state("u1")
    assert state.user_id == "u1"
    assert state.version == STATE_VERSION
    assert state.generated_at
    assert state.career_goal == ""
    assert state.frequent_mistakes == []  # no field_id given — never fabricated
    assert state.due_review_items == []
    assert state.motivation_signal["signal"] == "sin_datos"
    assert state.forgetting_risk["risk_level"] == "sin_datos"


def test_build_learning_state_surfaces_career_goal_and_academy_mistakes():
    _make_user()
    _make_enrollment()
    set_career_goal("u1", "Nurse")
    _record_mistake("u1", "f", "What is the past tense of 'to be'?", times=3)

    state = build_learning_state("u1", field_id="f")
    assert state.career_goal == "Nurse"
    assert state.frequent_mistakes[0]["question_text"] == "What is the past tense of 'to be'?"
    assert state.frequent_mistakes[0]["times_missed"] == 3


def test_build_learning_state_competencies_include_both_domains():
    _make_user()
    _make_enrollment()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.8)
    state = build_learning_state("u1", field_id="f")
    assert "academy" in state.competencies
    assert "language" in state.competencies


# ── LearningStateProvider ───────────────────────────────────────────────


def test_provider_caches_within_ttl():
    _make_user()
    provider = LearningStateProvider(ttl_s=999.0)
    first = provider.get("u1")

    # Mutate underlying data after the first read — a cached hit shouldn't see it.
    set_career_goal("u1", "Doctor")
    second = provider.get("u1")
    assert second is first
    assert second.career_goal == ""


def test_provider_force_refresh_bypasses_cache():
    _make_user()
    _make_enrollment()
    provider = LearningStateProvider(ttl_s=999.0)
    provider.get("u1")
    set_career_goal("u1", "Doctor")
    refreshed = provider.get("u1", force_refresh=True)
    assert refreshed.career_goal == "Doctor"


def test_provider_expires_after_ttl():
    _make_user()
    _make_enrollment()
    provider = LearningStateProvider(ttl_s=0.0)
    provider.get("u1")
    set_career_goal("u1", "Doctor")
    after = provider.get("u1")
    assert after.career_goal == "Doctor"


def test_provider_invalidate_drops_all_field_variants_for_user():
    _make_user()
    _make_enrollment()
    provider = LearningStateProvider(ttl_s=999.0)
    provider.get("u1")
    provider.get("u1", field_id="f")
    provider.invalidate("u1")
    set_career_goal("u1", "Doctor")
    assert provider.get("u1").career_goal == "Doctor"
    assert provider.get("u1", field_id="f").career_goal == "Doctor"


def test_provider_caches_separately_per_field_id():
    _make_user()
    _make_enrollment()
    _record_mistake("u1", "f", "q1", times=2)
    provider = LearningStateProvider(ttl_s=999.0)
    without_field = provider.get("u1")
    with_field = provider.get("u1", field_id="f")
    assert without_field.frequent_mistakes == []
    assert with_field.frequent_mistakes[0]["question_text"] == "q1"


# ── ConversationAdaptation ───────────────────────────────────────────────


def test_for_conversation_empty_when_state_has_nothing_actionable():
    _make_user()
    state = build_learning_state("u1")
    adaptation = for_conversation(state)
    assert adaptation.instructions == ""


def test_for_conversation_surfaces_career_goal():
    _make_user()
    _make_enrollment()
    set_career_goal("u1", "Software Engineer")
    state = build_learning_state("u1", field_id="f")
    adaptation = for_conversation(state)
    assert "Software Engineer" in adaptation.instructions


def test_for_conversation_surfaces_up_to_three_frequent_mistakes():
    _make_user()
    _make_enrollment()
    for i in range(5):
        _record_mistake("u1", "f", f"question {i}", times=1)
    state = build_learning_state("u1", field_id="f")
    adaptation = for_conversation(state)
    assert adaptation.instructions.count("question ") == 3
