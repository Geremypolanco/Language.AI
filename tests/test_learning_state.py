from backend import db
from backend.learning_engine import competency
from backend.learning_engine.adaptation import for_conversation, for_curriculum
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


def _insert_due_vocab(user_id, vocab_key, unit_id, target_text="hola"):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text, unit_id) "
            "VALUES (?, ?, ?, ?, 'hello', ?)",
            (user_id, vocab_key, db.now_iso(), target_text, unit_id),
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


# ── CurriculumAdaptation ─────────────────────────────────────────────────


def test_for_curriculum_empty_when_nothing_due():
    _make_user()
    state = build_learning_state("u1")
    adaptation = for_curriculum(state)
    assert adaptation.unit_weights == {}
    assert adaptation.weight_for("A1-0") == 0.0


def test_for_curriculum_weights_units_with_due_review_items():
    _make_user()
    _insert_due_vocab("u1", "A1-0.hola", "A1-0")
    _insert_due_vocab("u1", "A1-3.gracias", "A1-3")
    _insert_due_vocab("u1", "A1-3.adios", "A1-3")

    state = build_learning_state("u1")
    adaptation = for_curriculum(state)

    assert adaptation.weight_for("A1-0") == 1.0
    assert adaptation.weight_for("A1-3") == 2.0  # two due items in the same unit
    assert adaptation.weight_for("A1-9") == 0.0  # untouched unit stays neutral


def test_for_curriculum_ignores_due_items_with_no_unit_id():
    # unit_id defaults to '' for vocab_progress rows predating that column
    # (see db.py's migration) — a real case, not just a malformed input.
    _make_user()
    _insert_due_vocab("u1", "legacy.hola", unit_id="")
    state = build_learning_state("u1")
    adaptation = for_curriculum(state)
    assert adaptation.unit_weights == {}


def test_for_curriculum_ignores_academic_concept_review_items():
    _make_user()
    _make_enrollment()
    # Academic concept review reuses vocab_progress with an "academic:" prefixed
    # vocab_key and no real language unit_id — build_learning_state's
    # due_review_items already excludes these (exclude_prefix="academic:").
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text, unit_id) "
            "VALUES ('u1', 'academic:f:BACHELOR:0::variables', ?, 'Variables', 'def', '')",
            (db.now_iso(),),
        )
    state = build_learning_state("u1", field_id="f")
    adaptation = for_curriculum(state)
    assert adaptation.unit_weights == {}
