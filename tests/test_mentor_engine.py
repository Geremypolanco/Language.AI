import asyncio
import json
from datetime import UTC, datetime, timedelta

from backend import db
from backend.curriculum import units_for_level
from backend.learning_engine import competency, knowledge_graph
from backend.learning_engine import goals as goals_module
from backend.mentor_engine import (
    adaptive_mentor,
    concept_graph,
    conversation_memory_adapter,
    daily_planner,
    goal_planner,
    insights,
    knowledge_profile,
    mentor_engine,
    recommendation_engine,
)
from backend.models import CEFRLevel


def _make_user(user_id="u1"):
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO users
               (id, display_name, native_lang, target_lang, level, interests, xp, streak_days,
                gems, streak_freezes, created_at, last_active_date)
               VALUES (?, 'Test', 'en', 'es', 'A1', '[]', 0, 0, 0, 0, ?, ?)""",
            (user_id, db.now_iso(), db.today_str()),
        )


def _save_concept(concept_id, field_id, course_id, term, definition="def"):
    knowledge_graph.save_concepts(
        [{"id": concept_id, "field_id": field_id, "course_id": course_id, "term": term, "definition": definition}]
    )


def _insert_vocab_progress(user_id, vocab_key, repetitions=0, mistake_count=0, ease_factor=2.5):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, repetitions, mistake_count, ease_factor, due_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, vocab_key, repetitions, mistake_count, ease_factor, db.now_iso()),
        )


# ── Knowledge Profile ─────────────────────────────────────────────────────


def test_knowledge_profile_empty_for_field_with_no_concepts():
    _make_user()
    assert knowledge_profile.get_knowledge_profile("u1", "no-such-field") == []


def test_knowledge_profile_unknown_when_never_reviewed():
    _make_user()
    _save_concept("f:BACHELOR:0::variables", "f", "f:BACHELOR:0", "Variables")
    result = knowledge_profile.get_knowledge_profile("u1", "f")
    assert result == [{"concept_id": "f:BACHELOR:0::variables", "course_id": "f:BACHELOR:0", "term": "Variables", "status": "unknown"}]


def test_knowledge_profile_status_bands():
    _make_user()
    _save_concept("f:BACHELOR:0::a", "f", "f:BACHELOR:0", "A")
    _save_concept("f:BACHELOR:0::b", "f", "f:BACHELOR:0", "B")
    _save_concept("f:BACHELOR:0::c", "f", "f:BACHELOR:0", "C")
    _save_concept("f:BACHELOR:0::d", "f", "f:BACHELOR:0", "D")

    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::a", repetitions=1)
    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::b", repetitions=4)
    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::c", repetitions=8, mistake_count=1)
    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::d", repetitions=8, mistake_count=0, ease_factor=2.6)

    by_id = {c["concept_id"]: c["status"] for c in knowledge_profile.get_knowledge_profile("u1", "f")}
    assert by_id["f:BACHELOR:0::a"] == "learning"
    assert by_id["f:BACHELOR:0::b"] == "practicing"
    assert by_id["f:BACHELOR:0::c"] == "mastered"
    assert by_id["f:BACHELOR:0::d"] == "expert"


def test_weak_concepts_filters_to_unknown_and_learning():
    _make_user()
    _save_concept("f:BACHELOR:0::a", "f", "f:BACHELOR:0", "A")
    _save_concept("f:BACHELOR:0::b", "f", "f:BACHELOR:0", "B")
    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::b", repetitions=8, mistake_count=0, ease_factor=2.6)

    weak = knowledge_profile.weak_concepts("u1", "f")
    assert [c["concept_id"] for c in weak] == ["f:BACHELOR:0::a"]


# ── Concept graph (course-level blocker detection) ────────────────────────


def test_find_blockers_flags_weak_and_unattempted_prerequisites():
    _make_user()
    knowledge_graph.record_relation("f:BACHELOR:0", "f:BACHELOR:1", "prerequisite_of")
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.3)  # weak prerequisite

    blockers = concept_graph.find_blockers("u1", "f:BACHELOR:1")
    assert blockers == [{"course_id": "f:BACHELOR:0", "score": 0.3}]


def test_find_blockers_empty_when_prerequisite_is_solid():
    _make_user()
    knowledge_graph.record_relation("f:BACHELOR:0", "f:BACHELOR:1", "prerequisite_of")
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)

    assert concept_graph.find_blockers("u1", "f:BACHELOR:1") == []


def test_likely_root_cause_picks_the_weakest_blocker():
    _make_user()
    knowledge_graph.record_relation("f:BACHELOR:0", "f:BACHELOR:2", "prerequisite_of")
    knowledge_graph.record_relation("f:BACHELOR:1", "f:BACHELOR:2", "prerequisite_of")
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.4)
    competency.record_result("u1", "f", "f:BACHELOR:1", 0.1)

    root = concept_graph.likely_root_cause("u1", "f:BACHELOR:2")
    assert root["course_id"] == "f:BACHELOR:1"


def test_likely_root_cause_none_when_no_blockers():
    _make_user()
    assert concept_graph.likely_root_cause("u1", "f:BACHELOR:5") is None


# ── Intelligent Recommendations ───────────────────────────────────────────


_TITLES = {f"f:BACHELOR:{i}": f"Curso {i}" for i in range(5)}


def _insert_quiz_submission(user_id, course_id, kind, score):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_quiz_submission (user_id, course_id, kind, score, submitted_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, course_id, kind, score, db.now_iso()),
        )


def _insert_assignment_submission(user_id, course_id, assignment_id):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_assignment_submission (user_id, course_id, assignment_id, response, feedback, grade, submitted_at) "
            "VALUES (?, ?, ?, 'r', 'f', 'Bien', ?)",
            (user_id, course_id, assignment_id, db.now_iso()),
        )


def _insert_scenario_submission(user_id, course_id):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_scenario_submission (user_id, course_id, scenario, response, feedback, submitted_at) "
            "VALUES (?, ?, 'sc', 'r', 'f', ?)",
            (user_id, course_id, db.now_iso()),
        )


def test_review_recommendations_surface_due_concepts_and_vocab():
    _make_user()
    _save_concept("f:BACHELOR:0::a", "f", "f:BACHELOR:0", "A concept")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text) "
            "VALUES ('u1', 'academic:f:BACHELOR:0::a', ?, 'A concept', 'definition')",
            (db.now_iso(),),
        )
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at, target_text, native_text) "
            "VALUES ('u1', 'greetings.hello', ?, 'hola', 'hello')",
            (db.now_iso(),),
        )
    recs = recommendation_engine._review_recommendations("u1")
    actions = [r["action"] for r in recs]
    assert actions.count("review") == 2
    assert all(r["reason"] for r in recs)


def test_advance_and_reinforce_recommendations():
    _make_user()
    course_ids = list(_TITLES.keys())
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.3)  # weak -> exercises
    recs = recommendation_engine._advance_and_reinforce_recommendations("u1", "f", course_ids, _TITLES)
    actions = {r["action"] for r in recs}
    assert "exercises" in actions
    assert "advance" in actions
    assert all(r["reason"] for r in recs)


def test_retake_exam_recommendation_when_last_exam_score_low():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "exam", 0.9)
    _insert_quiz_submission("u1", "f:BACHELOR:0", "exam", 0.3)  # most recent (higher id) wins
    recs = recommendation_engine._retake_exam_recommendations("u1", _TITLES)
    assert len(recs) == 1
    assert recs[0]["action"] == "retake_exam"
    assert recs[0]["target"] == "f:BACHELOR:0"
    assert recs[0]["reason"]


def test_retake_exam_recommendation_absent_when_last_score_is_good():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "exam", 0.3)
    _insert_quiz_submission("u1", "f:BACHELOR:0", "exam", 0.9)  # most recent
    assert recommendation_engine._retake_exam_recommendations("u1", _TITLES) == []


def test_lab_recommendation_for_partial_assignment_submission():
    _make_user()
    _insert_assignment_submission("u1", "f:BACHELOR:0", "f:BACHELOR:0:0")
    recs = recommendation_engine._lab_recommendations("u1", list(_TITLES.keys()), _TITLES)
    assert len(recs) == 1
    assert recs[0]["action"] == "lab"
    assert recs[0]["evidence"]["submitted"] == 1


def test_lab_recommendation_absent_once_all_assignments_submitted():
    _make_user()
    for i in range(3):
        _insert_assignment_submission("u1", "f:BACHELOR:0", f"f:BACHELOR:0:{i}")
    assert recommendation_engine._lab_recommendations("u1", list(_TITLES.keys()), _TITLES) == []


def test_simulation_recommendation_for_mastered_course_without_scenario():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)
    rec = recommendation_engine._simulation_recommendation("u1", list(_TITLES.keys()), _TITLES)
    assert rec is not None
    assert rec["action"] == "simulation"
    assert rec["target"] == "f:BACHELOR:0"


def test_simulation_recommendation_absent_once_already_done():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)
    _insert_scenario_submission("u1", "f:BACHELOR:0")
    assert recommendation_engine._simulation_recommendation("u1", list(_TITLES.keys()), _TITLES) is None


def test_motivation_recommendation_rest_when_frustrated_and_high_dropout_risk():
    _make_user("u1")
    with db.cursor() as cur:
        for score in [0.2, 0.1, 0.15]:
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES ('u1', 'u0', ?, ?)",
                (score, db.now_iso()),
            )
        cur.execute(
            "UPDATE users SET last_active_date=?, streak_days=0 WHERE id='u1'",
            ((datetime.fromisoformat(db.today_str()) - timedelta(days=5)).date().isoformat(),),
        )
    recs = recommendation_engine._motivation_recommendations("u1")
    assert len(recs) == 1
    assert recs[0]["action"] == "rest"


def test_motivation_recommendation_tutor_conversation_when_just_frustrated():
    _make_user("u1")
    with db.cursor() as cur:
        for score in [0.2, 0.1, 0.15]:
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES ('u1', 'u0', ?, ?)",
                (score, db.now_iso()),
            )
    recs = recommendation_engine._motivation_recommendations("u1")
    assert len(recs) == 1
    assert recs[0]["action"] == "tutor_conversation"


def test_generate_recommendations_every_item_has_a_reason():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.3)
    recs = recommendation_engine.generate_recommendations("u1", "f", list(_TITLES.keys()), _TITLES)
    assert len(recs) > 0
    assert all(r["reason"] for r in recs)
    assert all(r["action"] and "evidence" in r for r in recs)


# ── Daily Learning Plan ────────────────────────────────────────────────────


def test_language_next_unit_skips_mastered_units():
    _make_user()
    units = units_for_level(CEFRLevel.A1)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO unit_mastery (user_id, unit_id, best_score, attempts, mastered) VALUES ('u1', ?, 1.0, 1, 1)",
            (units[0].id,),
        )
    rec = daily_planner._language_next_unit("u1", CEFRLevel.A1)
    assert rec["target"] == units[1].id


def test_conversation_practice_recommendation_only_when_no_turns_today():
    _make_user()
    assert daily_planner._conversation_practice_recommendation("u1") is not None
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO conversation_log (user_id, role, content, created_at) VALUES ('u1', 'user', 'hola', ?)",
            (db.now_iso(),),
        )
    assert daily_planner._conversation_practice_recommendation("u1") is None


def test_build_daily_plan_rest_overrides_everything_else():
    _make_user("u1")
    with db.cursor() as cur:
        for score in [0.1, 0.2, 0.15]:
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES ('u1', 'u0', ?, ?)",
                (score, db.now_iso()),
            )
        cur.execute(
            "UPDATE users SET last_active_date=?, streak_days=0 WHERE id='u1'",
            ((datetime.fromisoformat(db.today_str()) - timedelta(days=5)).date().isoformat(),),
        )
    plan = daily_planner.build_daily_plan("u1", "f", list(_TITLES.keys()), _TITLES, CEFRLevel.A1)
    assert len(plan) == 1
    assert plan[0]["action"] == "rest"


def test_build_daily_plan_caps_items_and_dedupes_by_action():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.3)
    plan = daily_planner.build_daily_plan("u1", "f", list(_TITLES.keys()), _TITLES, CEFRLevel.A1)
    assert len(plan) <= daily_planner._MAX_PLAN_ITEMS
    actions = [item["action"] for item in plan]
    assert len(actions) == len(set(actions))
    assert all(item["reason"] for item in plan)


def test_build_daily_plan_works_without_academy_enrollment():
    _make_user()
    plan = daily_planner.build_daily_plan("u1", None, [], {}, CEFRLevel.A1)
    # Still gets a real plan: at least the language "next unit" + conversation nudge.
    assert any(item["action"] == "advance" for item in plan)
    assert all(item["reason"] for item in plan)


# ── Mentor Insights ──────────────────────────────────────────────────────


def test_quiz_trend_insight_detects_improvement():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.4)
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.8)
    result = insights._quiz_trend_insights("u1", _TITLES)
    assert len(result) == 1
    assert result[0]["type"] == "improvement"


def test_quiz_trend_insight_detects_persistent_struggle():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.3)
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.2)
    result = insights._quiz_trend_insights("u1", _TITLES)
    assert len(result) == 1
    assert result[0]["type"] == "struggle"


def test_quiz_trend_insight_none_with_only_one_submission():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.9)
    assert insights._quiz_trend_insights("u1", _TITLES) == []


def test_mistake_concentration_insight_picks_the_worst_course():
    _make_user()
    with db.cursor() as cur:
        for _ in range(1):
            cur.execute(
                "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES ('u1', 'f:BACHELOR:0', 'quiz', 0, 'q1', 0, ?)",
                (db.now_iso(),),
            )
        for _ in range(3):
            cur.execute(
                "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES ('u1', 'f:BACHELOR:1', 'quiz', 0, 'q2', 0, ?)",
                (db.now_iso(),),
            )
    result = insights._mistake_concentration_insight("u1", "f", _TITLES)
    assert result["evidence"]["course_id"] == "f:BACHELOR:1"


def test_mastery_transition_insight_when_ready_to_advance():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)
    result = insights._mastery_transition_insight("u1", "f", list(_TITLES.keys()), _TITLES)
    assert result["evidence"]["mastered_course_id"] == "f:BACHELOR:0"
    assert result["evidence"]["next_course_id"] == "f:BACHELOR:1"


def test_generate_insights_combines_everything():
    _make_user()
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.3)
    _insert_quiz_submission("u1", "f:BACHELOR:0", "quiz", 0.9)
    result = insights.generate_insights("u1", "f", list(_TITLES.keys()), _TITLES)
    assert any(i["type"] == "improvement" for i in result)
    assert all(i["message"] for i in result)


# ── Adaptive Mentor ─────────────────────────────────────────────────────


def test_mentor_mode_neutral_with_no_signal():
    _make_user()
    result = adaptive_mentor.get_mentor_mode("u1")
    assert result["mode"] == "neutral"
    assert result["directives"] == []
    assert adaptive_mentor.mode_instruction_text(result) == ""


def test_mentor_mode_apoyo_on_frustration():
    _make_user("u1")
    with db.cursor() as cur:
        for score in [0.1, 0.2, 0.15]:
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES ('u1', 'u0', ?, ?)",
                (score, db.now_iso()),
            )
    result = adaptive_mentor.get_mentor_mode("u1")
    assert result["mode"] == "apoyo"
    assert result["directives"]
    assert "APOYO" in adaptive_mentor.mode_instruction_text(result)


def test_mentor_mode_reto_on_strong_momentum():
    _make_user("u1")
    with db.cursor() as cur:
        for score in [0.9, 0.95, 1.0]:
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES ('u1', 'u0', ?, ?)",
                (score, db.now_iso()),
            )
    result = adaptive_mentor.get_mentor_mode("u1")
    assert result["mode"] == "reto"


def test_mentor_mode_falls_back_to_course_difficulty_signal():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.3)  # "reforzar" band
    result = adaptive_mentor.get_mentor_mode("u1", course_id="f:BACHELOR:0")
    assert result["mode"] == "apoyo"
    assert result["evidence"]["difficulty_signal"] == "reforzar"


# ── Conversation Memory Adapter ───────────────────────────────────────────


def test_get_memory_empty_when_never_set():
    _make_user()
    assert conversation_memory_adapter.get_memory("u1") == ""


def test_get_memory_reads_what_conversation_router_writes():
    _make_user()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO user_memories (user_id, content, updated_at) VALUES ('u1', 'ayer vimos recursión', ?)",
            (db.now_iso(),),
        )
    assert conversation_memory_adapter.get_memory("u1") == "ayer vimos recursión"


def test_has_recent_conversation_false_when_none_and_true_when_fresh():
    _make_user()
    assert conversation_memory_adapter.has_recent_conversation("u1") is False
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO user_memories (user_id, content, updated_at) VALUES ('u1', 'x', ?)",
            (db.now_iso(),),
        )
    assert conversation_memory_adapter.has_recent_conversation("u1") is True


def test_has_recent_conversation_false_when_stale():
    _make_user()
    stale = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    with db.cursor() as cur:
        cur.execute("INSERT INTO user_memories (user_id, content, updated_at) VALUES ('u1', 'x', ?)", (stale,))
    assert conversation_memory_adapter.has_recent_conversation("u1", within_hours=24) is False


# ── Goal Planner (AI milestone generation) ────────────────────────────────


_VALID_MILESTONES_JSON = json.dumps(
    ["Aprender Python", "Dominar Algoritmos", "Aprender Machine Learning", "Construir proyectos"]
)


def test_generate_milestones_success(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return _VALID_MILESTONES_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    result = asyncio.run(goal_planner.generate_milestones("Convertirme en AI Engineer"))
    assert result == ["Aprender Python", "Dominar Algoritmos", "Aprender Machine Learning", "Construir proyectos"]


def test_generate_milestones_retries_then_succeeds(monkeypatch):
    from backend import hf_client as hf_client_module

    responses = iter(["not json", _VALID_MILESTONES_JSON])

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(responses)

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    result = asyncio.run(goal_planner.generate_milestones("Convertirme en AI Engineer"))
    assert len(result) == 4


def test_generate_milestones_raises_after_exhausting_retries(monkeypatch):
    from backend import hf_client as hf_client_module

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    try:
        asyncio.run(goal_planner.generate_milestones("x"))
        assert False, "expected GenerationError"
    except goal_planner.GenerationError:
        pass


def test_validate_milestones_rejects_too_few_and_duplicates():
    assert goal_planner._validate_milestones(["only one"]) != []
    assert goal_planner._validate_milestones(["A", "B", "a"]) != []  # case-insensitive dup, still short of 3 unique
    assert goal_planner._validate_milestones(["Aprender Python", "Dominar Algoritmos", "Construir proyectos"]) == []


def test_ensure_milestones_generates_once_and_persists(monkeypatch):
    from backend import hf_client as hf_client_module

    calls = []

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        calls.append(1)
        return _VALID_MILESTONES_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    _make_user()
    goal = goals_module.add_goal("u1", "Convertirme en AI Engineer")

    first = asyncio.run(goal_planner.ensure_milestones("u1", goal["id"]))
    assert len(first) == 4
    assert len(calls) == 1

    # Second call must not regenerate — milestones are already persisted.
    second = asyncio.run(goal_planner.ensure_milestones("u1", goal["id"]))
    assert second == first
    assert len(calls) == 1


def test_ensure_milestones_falls_back_to_goal_text_on_generation_failure(monkeypatch):
    from backend import hf_client as hf_client_module

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    _make_user()
    goal = goals_module.add_goal("u1", "Meta sin desglosar")

    result = asyncio.run(goal_planner.ensure_milestones("u1", goal["id"]))
    assert result == ["Meta sin desglosar"]


def test_ensure_milestones_raises_for_unknown_goal():
    _make_user()
    try:
        asyncio.run(goal_planner.ensure_milestones("u1", 999999))
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── Mentor Dashboard (orchestrator) ────────────────────────────────────────


def test_mentor_dashboard_works_without_academy_enrollment():
    _make_user()
    dashboard = mentor_engine.get_mentor_dashboard("u1", None, [], {}, level=CEFRLevel.A1)
    assert dashboard["status"]["mentor_mode"] == "neutral"
    assert dashboard["goals"] == []
    assert dashboard["mastered_concepts"] == []
    assert dashboard["weak_concepts"] == []
    assert dashboard["strengths_and_weaknesses"] == {"strengths": [], "weaknesses": []}
    assert dashboard["competencies"] == {"academy": [], "language": []}
    assert "daily_plan" in dashboard
    assert "risks" in dashboard


def test_mentor_dashboard_combines_everything_with_a_real_enrollment():
    _make_user()
    _save_concept("f:BACHELOR:0::a", "f", "f:BACHELOR:0", "A concept")
    _insert_vocab_progress("u1", "academic:f:BACHELOR:0::a", repetitions=8, mistake_count=0, ease_factor=2.6)
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)
    goal = goals_module.add_goal("u1", "Terminar la carrera")
    goals_module.set_milestones("u1", goal["id"], ["Paso 1", "Paso 2", "Paso 3"])

    dashboard = mentor_engine.get_mentor_dashboard("u1", "f", list(_TITLES.keys()), _TITLES, level=CEFRLevel.A1)

    assert dashboard["goals"][0]["text"] == "Terminar la carrera"
    assert dashboard["next_milestones"][0]["current_milestone"] == "Paso 1"
    assert any(c["concept_id"] == "f:BACHELOR:0::a" for c in dashboard["mastered_concepts"])
    assert dashboard["competencies"]["academy"][0]["course_id"] == "f:BACHELOR:0"
    assert isinstance(dashboard["recommendations"], list)
    assert isinstance(dashboard["daily_plan"], list)
    assert dashboard["risks"]["forgetting_risk"]["risk_level"] in ("bajo", "medio", "alto", "sin_datos")
