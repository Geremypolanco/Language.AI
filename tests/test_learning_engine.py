import asyncio
from datetime import UTC, datetime, timedelta

from backend import academy, db
from backend.curriculum import units_for_level
from backend.learning_engine import (
    achievements,
    analytics,
    competency,
    concept_review,
    goals,
    grading,
    knowledge_graph,
    learning_style,
    motivation,
    portfolio,
    predictions,
    recommendations,
    student_profile,
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


# ── Knowledge graph ──────────────────────────────────────────────────────


def test_concepts_from_glossary_and_save_roundtrip():
    glossary = {"terms": [{"term": "Recursion", "definition": "A function calling itself"}, {"term": "Stack", "definition": "LIFO structure"}]}
    concepts = knowledge_graph.concepts_from_glossary("computer-science", "computer-science:BACHELOR:0", glossary)
    assert len(concepts) == 2
    knowledge_graph.save_concepts(concepts)

    fetched = knowledge_graph.concepts_for_course("computer-science:BACHELOR:0")
    assert {c["term"] for c in fetched} == {"Recursion", "Stack"}
    assert knowledge_graph.graph_exists_for("computer-science")
    assert not knowledge_graph.graph_exists_for("no-such-field")


def test_get_concept_by_id():
    glossary = {"terms": [{"term": "Big O", "definition": "Asymptotic complexity notation"}]}
    concepts = knowledge_graph.concepts_from_glossary("computer-science", "computer-science:BACHELOR:1", glossary)
    knowledge_graph.save_concepts(concepts)
    concept_id = concepts[0]["id"]

    fetched = knowledge_graph.get_concept(concept_id)
    assert fetched["term"] == "Big O"
    assert knowledge_graph.get_concept("does-not-exist") is None


def test_build_graph_for_field_level_derives_concepts_and_prerequisite_chain():
    class _FakeStore:
        def __init__(self, glossaries):
            self.glossaries = glossaries

        def load_course_asset(self, field_id, level, course_id, kind, version=None):
            if kind == "glossary":
                return self.glossaries.get(course_id)
            return None

    course_ids = ["f:BACHELOR:0", "f:BACHELOR:1", "f:BACHELOR:2"]
    glossaries = {
        "f:BACHELOR:0": {"terms": [{"term": "A", "definition": "a"}]},
        "f:BACHELOR:1": {"terms": [{"term": "B", "definition": "b"}]},
        # course 2 has no glossary built yet — should be skipped, not an error
    }
    added = knowledge_graph.build_graph_for_field_level("f", "BACHELOR", course_ids, _FakeStore(glossaries))
    assert added == 2
    assert knowledge_graph.concepts_for_course("f:BACHELOR:0")
    assert knowledge_graph.concepts_for_course("f:BACHELOR:2") == []
    assert knowledge_graph.prerequisite_courses("f:BACHELOR:1") == ["f:BACHELOR:0"]
    assert knowledge_graph.prerequisite_courses("f:BACHELOR:2") == ["f:BACHELOR:1"]
    assert knowledge_graph.prerequisite_courses("f:BACHELOR:0") == []


def test_record_relation_rejects_unknown_type():
    try:
        knowledge_graph.record_relation("a", "b", "not_a_real_relation")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── Competency ───────────────────────────────────────────────────────────


def test_record_result_and_get_competency():
    _make_user()
    score = competency.record_result("u1", "computer-science", "computer-science:BACHELOR:0", 0.9)
    assert score == 0.9  # first attempt: no smoothing yet
    comp = competency.get_competency("u1", "computer-science:BACHELOR:0")
    assert comp["score"] == 0.9
    assert comp["attempts"] == 1


def test_record_result_uses_exponential_moving_average():
    _make_user()
    competency.record_result("u1", "f", "c1", 1.0)
    second = competency.record_result("u1", "f", "c1", 0.0)
    # A single bad result shouldn't crater a good track record to 0.
    assert 0.0 < second < 1.0
    comp = competency.get_competency("u1", "c1")
    assert comp["attempts"] == 2


def test_is_mastered_threshold():
    _make_user()
    competency.record_result("u1", "f", "c1", 0.9)
    competency.record_result("u1", "f", "c2", 0.3)
    assert competency.is_mastered("u1", "c1") is True
    assert competency.is_mastered("u1", "c2") is False
    assert competency.is_mastered("u1", "does-not-exist") is False


def test_strengths_and_weaknesses():
    _make_user()
    competency.record_result("u1", "f", "strong", 0.95)
    competency.record_result("u1", "f", "weak", 0.2)
    result = competency.strengths_and_weaknesses("u1", "f", top_n=1)
    assert result["strengths"][0]["course_id"] == "strong"
    assert result["weaknesses"][0]["course_id"] == "weak"


def test_get_language_competencies_reuses_unit_mastery_not_a_new_table():
    _make_user()
    unit = units_for_level(CEFRLevel.A1)[1]
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO unit_mastery (user_id, unit_id, best_score, attempts, mastered) VALUES (?, ?, 0.75, 2, 0)",
            ("u1", unit.id),
        )
    result = competency.get_language_competencies("u1")
    assert len(result) == 1
    assert result[0]["unit_id"] == unit.id
    assert result[0]["score"] == 0.75
    assert result[0]["mastered"] is False


def test_get_language_competencies_empty_for_untouched_units():
    _make_user()
    assert competency.get_language_competencies("u1") == []


def test_get_unified_competencies_presents_both_domains_separately():
    _make_user()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.9)
    unit = units_for_level(CEFRLevel.A1)[1]
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO unit_mastery (user_id, unit_id, best_score, attempts, mastered) VALUES (?, ?, 0.6, 1, 0)",
            ("u1", unit.id),
        )
    unified = competency.get_unified_competencies("u1", "f")
    assert unified["academy"][0]["course_id"] == "f:BACHELOR:0"
    assert unified["language"][0]["unit_id"] == unit.id
    assert set(unified.keys()) == {"academy", "language"}  # never blended into one number


# ── Grading ──────────────────────────────────────────────────────────────


def test_grade_submission_auto_grades_multiple_choice_and_true_false():
    questions = [
        {"type": "multiple_choice", "question": "q1", "options": ["a", "b"], "correct_answer": "a"},
        {"type": "true_false", "question": "q2", "correct_answer": True},
    ]
    result = asyncio.run(grading.grade_submission(questions, {"0": "a", "1": "True"}, "es"))
    assert result["score"] == 1.0
    result_wrong = asyncio.run(grading.grade_submission(questions, {"0": "b", "1": "False"}, "es"))
    assert result_wrong["score"] == 0.0


def test_grade_submission_missing_answer_counts_as_wrong():
    questions = [{"type": "multiple_choice", "question": "q", "options": ["a", "b"], "correct_answer": "a"}]
    result = asyncio.run(grading.grade_submission(questions, {}, "es"))
    assert result["score"] == 0.0


def test_grade_submission_grades_open_questions_via_ai(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_grade_open_answer(question, rubric_note, student_answer, native_lang):
        return (student_answer == "good answer"), "feedback text"

    monkeypatch.setattr(hf_client_module.hf_client, "grade_open_answer", fake_grade_open_answer)
    questions = [{"type": "open", "question": "q", "rubric_note": "must mention X"}]
    result = asyncio.run(grading.grade_submission(questions, {"0": "good answer"}, "es"))
    assert result["score"] == 1.0
    assert result["results"][0]["feedback"] == "feedback text"


# ── Recommendations ──────────────────────────────────────────────────────


def test_recommend_next_course_skips_mastered():
    _make_user()
    competency.record_result("u1", "f", "c0", 0.9)
    next_course = recommendations.recommend_next_course("u1", "f", ["c0", "c1", "c2"])
    assert next_course == "c1"


def test_recommend_next_course_returns_none_when_all_mastered():
    _make_user()
    for cid in ["c0", "c1"]:
        competency.record_result("u1", "f", cid, 0.95)
    assert recommendations.recommend_next_course("u1", "f", ["c0", "c1"]) is None


def test_courses_needing_review_only_lists_weak_attempted_courses():
    _make_user()
    competency.record_result("u1", "f", "weak", 0.3)
    competency.record_result("u1", "f", "strong", 0.9)
    result = recommendations.courses_needing_review("u1", "f", ["strong", "weak", "never-attempted"])
    assert result == ["weak"]


def test_suggest_specializations_uses_real_activated_fields():
    specializations = recommendations.suggest_specializations("computer-science")
    ids = {f.id for f in specializations}
    assert {"artificial-intelligence", "cybersecurity", "cryptography", "quantum-computing", "robotics"} <= ids
    assert recommendations.suggest_specializations("does-not-exist") == []
    # Every field claiming to specialize on computer-science must be a real,
    # resolvable field, not a dangling reference.
    for f in specializations:
        assert academy.get_field(f.id) is not None


def test_difficulty_signal_bands():
    _make_user()
    competency.record_result("u1", "f", "weak", 0.3)
    competency.record_result("u1", "f", "strong", 0.9)
    competency.record_result("u1", "f", "steady", 0.65)
    assert recommendations.difficulty_signal("u1", "weak") == "reforzar"
    assert recommendations.difficulty_signal("u1", "strong") == "avanzar"
    assert recommendations.difficulty_signal("u1", "steady") == "constante"
    assert recommendations.difficulty_signal("u1", "never-attempted") == "constante"


# ── Achievements ─────────────────────────────────────────────────────────


def test_mastered_course_achievements_uses_titles_when_given():
    _make_user()
    competency.record_result("u1", "f", "c1", 0.9)
    result = achievements.mastered_course_achievements("u1", "f", {"c1": "Estructuras de Datos"})
    assert result[0]["title"] == "Dominado: Estructuras de Datos"


def test_completion_achievements_only_at_real_milestones():
    _make_user()
    with db.cursor() as cur:
        for i in range(5):
            cur.execute(
                "INSERT INTO academy_course_progress (user_id, course_id, completed_at) VALUES (?, ?, ?)",
                ("u1", f"c{i}", db.now_iso()),
            )
    result = achievements.completion_achievements("u1")
    assert {a["threshold"] for a in result} == {5}


# ── Concept review (reuses srs.py) ───────────────────────────────────────


def test_concept_review_record_and_due(monkeypatch):
    _make_user()
    from datetime import UTC, datetime, timedelta

    concept_review.record_answer("u1", "cs:0::recursion", correct=False, concept_term="Recursion", concept_definition="calls itself")
    with db.cursor() as cur:
        cur.execute(
            "UPDATE vocab_progress SET due_at=? WHERE vocab_key=?",
            ((datetime.now(UTC) - timedelta(days=1)).isoformat(), concept_review.concept_vocab_key("cs:0::recursion")),
        )
    due = concept_review.due_concepts("u1")
    assert len(due) == 1
    assert due[0]["target_text"] == "Recursion"


def test_concept_review_never_mixes_with_language_vocab():
    from backend import srs

    _make_user()
    srs.schedule_review("u1", "greetings.hello", quality=1, target_text="Hola", native_text="Hello")
    concept_review.record_answer("u1", "cs:0::recursion", correct=False, concept_term="Recursion", concept_definition="calls itself")
    with db.cursor() as cur:
        cur.execute("UPDATE vocab_progress SET due_at = '2000-01-01T00:00:00+00:00'")

    academic_due = concept_review.due_concepts("u1")
    language_due = srs.due_review_items("u1", exclude_prefix="academic:")
    assert [d["vocab_key"] for d in academic_due] == [concept_review.concept_vocab_key("cs:0::recursion")]
    assert [d["vocab_key"] for d in language_due] == ["greetings.hello"]


def test_is_concept_vocab_key_and_strip():
    key = concept_review.concept_vocab_key("cs:0::recursion")
    assert concept_review.is_concept_vocab_key(key)
    assert not concept_review.is_concept_vocab_key("greetings.hello")
    assert concept_review.concept_id_from_vocab_key(key) == "cs:0::recursion"


# ── Analytics ────────────────────────────────────────────────────────────


def test_student_summary_combines_competency_time_and_recommendation():
    _make_user()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES (?, ?, ?, ?)",
            ("u1", "f:BACHELOR:0", db.now_iso(), 120),
        )
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.95)

    summary = analytics.student_summary("u1", "f", ["f:BACHELOR:0", "f:BACHELOR:1"], {"f:BACHELOR:0": "Curso A", "f:BACHELOR:1": "Curso B"})
    assert summary["courses_completed"] == 1
    assert summary["total_time_minutes"] == 2
    assert summary["competencies"][0]["title"] == "Curso A"
    assert summary["next_course_id"] == "f:BACHELOR:1"  # not yet mastered
    assert summary["next_course_title"] == "Curso B"


def test_field_summary_surfaces_most_failed_questions_and_aggregate_scores():
    _make_user("u1")
    _make_user("u2")
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.8)
    competency.record_result("u2", "f", "f:BACHELOR:0", 0.4)
    with db.cursor() as cur:
        for user_id, correct in [("u1", 1), ("u2", 0)]:
            cur.execute(
                "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES (?, 'f:BACHELOR:0', 'quiz', 0, 'q0?', ?, ?)",
                (user_id, correct, db.now_iso()),
            )
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES ('u1', 'f:BACHELOR:0', ?, 60)",
            (db.now_iso(),),
        )

    summary = analytics.field_summary("f")
    assert summary["most_failed_questions"][0]["question_text"] == "q0?"
    assert summary["most_failed_questions"][0]["failures"] == 1
    scores = {row["course_id"]: row["avg_score"] for row in summary["avg_competency_by_course"]}
    assert abs(scores["f:BACHELOR:0"] - 0.6) < 1e-9
    assert summary["completions_by_course"][0]["completions"] == 1


# ── Portfolio ────────────────────────────────────────────────────────────


def test_get_portfolio_aggregates_assignments_scenarios_and_completions():
    _make_user()
    now = db.now_iso()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_assignment_submission (user_id, course_id, assignment_id, response, feedback, grade, submitted_at) "
            "VALUES ('u1', 'f:BACHELOR:0', 'f:BACHELOR:0:0', 'my response', 'good job', 'Bien', ?)",
            (now,),
        )
        cur.execute(
            "INSERT INTO academy_scenario_submission (user_id, course_id, scenario, response, feedback, submitted_at) "
            "VALUES ('u1', 'f:BACHELOR:0', 'a scenario', 'my answer', 'nice work', ?)",
            (now,),
        )
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES ('u1', 'f:BACHELOR:0', ?, 300)",
            (now,),
        )

    result = portfolio.get_portfolio("u1")
    assert result["assignments"][0]["response"] == "my response"
    assert result["scenarios"][0]["feedback"] == "nice work"
    assert result["completed_courses"][0]["elapsed_seconds"] == 300
    # No quiz/exam graded yet for this course — competency_score is honestly None.
    assert result["assignments"][0]["competency_score"] is None


def test_get_portfolio_attaches_real_competency_score_to_each_item():
    _make_user()
    now = db.now_iso()
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.77)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_assignment_submission (user_id, course_id, assignment_id, response, feedback, grade, submitted_at) "
            "VALUES ('u1', 'f:BACHELOR:0', 'f:BACHELOR:0:0', 'r', 'f', 'Bien', ?)",
            (now,),
        )
    result = portfolio.get_portfolio("u1")
    assert result["assignments"][0]["competency_score"] == 0.77


def test_get_portfolio_empty_for_new_user():
    _make_user()
    result = portfolio.get_portfolio("u1")
    assert result == {"assignments": [], "scenarios": [], "completed_courses": []}


# ── Student profile (tutor memory) ───────────────────────────────────────


def _make_enrollment(user_id="u1", field_id="f", level="BACHELOR"):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_enrollment (user_id, field_id, level, enrolled_at, content_lang) VALUES (?, ?, ?, ?, 'es')",
            (user_id, field_id, level, db.now_iso()),
        )


def test_set_and_get_career_goal():
    _make_user()
    _make_enrollment()
    assert student_profile.get_career_goal("u1") == ""
    student_profile.set_career_goal("u1", "  AI Engineer  ")
    assert student_profile.get_career_goal("u1") == "AI Engineer"


def test_frequent_mistakes_scoped_to_user_and_field():
    _make_user("u1")
    _make_user("u2")
    with db.cursor() as cur:
        for _ in range(3):
            cur.execute(
                "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
                "VALUES ('u1', 'f:BACHELOR:0', 'quiz', 0, 'q missed a lot', 0, ?)",
                (db.now_iso(),),
            )
        cur.execute(
            "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
            "VALUES ('u2', 'f:BACHELOR:0', 'quiz', 0, 'q missed a lot', 0, ?)",
            (db.now_iso(),),
        )
        cur.execute(
            "INSERT INTO academy_question_attempt (user_id, course_id, kind, question_index, question_text, correct, submitted_at) "
            "VALUES ('u1', 'other-field:BACHELOR:0', 'quiz', 0, 'unrelated field question', 0, ?)",
            (db.now_iso(),),
        )
    result = student_profile.frequent_mistakes("u1", "f")
    assert len(result) == 1
    assert result[0]["question_text"] == "q missed a lot"
    assert result[0]["times_missed"] == 3  # only u1's own attempts, not u2's


def test_learning_velocity_relative_bands():
    _make_user("u1")
    _make_user("u2")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES ('u1', 'f:BACHELOR:0', ?, 60)",
            (db.now_iso(),),
        )
        cur.execute(
            "INSERT INTO academy_course_progress (user_id, course_id, completed_at, elapsed_seconds) VALUES ('u2', 'f:BACHELOR:0', ?, 600)",
            (db.now_iso(),),
        )
    result = student_profile.learning_velocity("u1", "f")
    assert result["relative"] == "más_rápido"  # far below the (60+600)/2=330 field average

    result_none = student_profile.learning_velocity("u1", "no-data-field")
    assert result_none["relative"] == "sin_datos"


def test_profile_summary_combines_everything():
    _make_user()
    _make_enrollment()
    student_profile.set_career_goal("u1", "Data Scientist")
    competency.record_result("u1", "f", "f:BACHELOR:0", 0.9)
    goals.add_goal("u1", "Terminar la carrera")

    summary = student_profile.profile_summary("u1", "f", ["music", "chess"])
    assert summary["career_goal"] == "Data Scientist"
    assert summary["interests"] == ["music", "chess"]
    assert "strengths_and_weaknesses" in summary
    assert "forgotten_concepts" in summary
    assert "learning_velocity" in summary
    # Learning Intelligence Engine additions — every sub-engine represented.
    assert summary["goals"][0]["text"] == "Terminar la carrera"
    assert summary["competencies"]["academy"][0]["course_id"] == "f:BACHELOR:0"
    assert summary["forgetting_risk"]["risk_level"] == "sin_datos"
    assert summary["dropout_risk"]["risk_level"] in ("sin_datos", "bajo")
    assert summary["learning_style"]["style"] == "sin_datos"
    assert summary["motivation"]["signal"] == "sin_datos"


def test_profile_summary_works_without_academy_enrollment():
    _make_user()
    summary = student_profile.profile_summary("u1", None, ["chess"])
    assert summary["strengths_and_weaknesses"] == {"strengths": [], "weaknesses": []}
    assert summary["frequent_mistakes"] == []
    assert summary["learning_velocity"]["relative"] == "sin_datos"
    assert summary["competencies"] == {"academy": [], "language": []}
    assert summary["goals"] == []


# ── Learning goals (multiple, ordered) ──────────────────────────────────


def test_add_goal_and_list_goals_in_order():
    _make_user()
    first = goals.add_goal("u1", "  Pasar el B2 de inglés  ")
    second = goals.add_goal("u1", "Terminar la especialización en IA")

    assert first["text"] == "Pasar el B2 de inglés"  # stripped
    assert first["sort_order"] == 0
    assert second["sort_order"] == 1
    assert first["completed"] is False

    listed = goals.list_goals("u1")
    assert [g["text"] for g in listed] == ["Pasar el B2 de inglés", "Terminar la especialización en IA"]


def test_goals_scoped_per_user():
    _make_user("u1")
    _make_user("u2")
    goals.add_goal("u1", "u1 goal")
    goals.add_goal("u2", "u2 goal")
    assert [g["text"] for g in goals.list_goals("u1")] == ["u1 goal"]
    assert [g["text"] for g in goals.list_goals("u2")] == ["u2 goal"]


def test_complete_goal_toggles_and_rejects_other_users_goal():
    _make_user("u1")
    _make_user("u2")
    goal = goals.add_goal("u1", "Practicar todos los días")

    assert goals.complete_goal("u1", goal["id"], True) is True
    assert goals.list_goals("u1")[0]["completed"] is True

    assert goals.complete_goal("u1", goal["id"], False) is True
    assert goals.list_goals("u1")[0]["completed"] is False

    # u2 can't complete u1's goal
    assert goals.complete_goal("u2", goal["id"], True) is False


def test_remove_goal_deletes_only_the_owners_row():
    _make_user("u1")
    _make_user("u2")
    goal = goals.add_goal("u1", "Meta temporal")

    assert goals.remove_goal("u2", goal["id"]) is False
    assert goals.list_goals("u1") != []

    assert goals.remove_goal("u1", goal["id"]) is True
    assert goals.list_goals("u1") == []


def test_new_goal_has_no_milestones_yet():
    _make_user()
    goal = goals.add_goal("u1", "Convertirme en AI Engineer")
    assert goal["milestones"] == []
    assert goal["milestone_progress"] == 0
    assert goal["current_milestone"] is None


def test_set_milestones_and_get_goal_reflects_current_milestone():
    _make_user()
    goal = goals.add_goal("u1", "Convertirme en AI Engineer")
    assert goals.set_milestones("u1", goal["id"], ["Aprender Python", "Dominar Algoritmos", "Aprender ML"]) is True

    fetched = goals.get_goal("u1", goal["id"])
    assert fetched["milestones"] == ["Aprender Python", "Dominar Algoritmos", "Aprender ML"]
    assert fetched["current_milestone"] == "Aprender Python"


def test_set_milestones_rejects_other_users_goal():
    _make_user("u1")
    _make_user("u2")
    goal = goals.add_goal("u1", "Meta")
    assert goals.set_milestones("u2", goal["id"], ["x"]) is False


def test_advance_milestone_moves_the_cursor_forward_and_caps_at_the_end():
    _make_user()
    goal = goals.add_goal("u1", "Convertirme en AI Engineer")
    goals.set_milestones("u1", goal["id"], ["Aprender Python", "Dominar Algoritmos"])

    after_first = goals.advance_milestone("u1", goal["id"])
    assert after_first["current_milestone"] == "Dominar Algoritmos"
    assert after_first["milestone_progress"] == 1

    after_second = goals.advance_milestone("u1", goal["id"])
    assert after_second["current_milestone"] is None  # no more milestones left
    assert after_second["milestone_progress"] == 2

    # Advancing past the end doesn't error or overflow the index.
    after_third = goals.advance_milestone("u1", goal["id"])
    assert after_third["milestone_progress"] == 2


def test_advance_milestone_returns_none_for_unknown_goal():
    _make_user()
    assert goals.advance_milestone("u1", 999999) is None


# ── Predictions (heuristics, not ML) ─────────────────────────────────────


def test_forgetting_risk_no_data():
    _make_user()
    result = predictions.forgetting_risk("u1")
    assert result == {"due_count": 0, "tracked_total": 0, "overdue_days_max": 0, "risk_level": "sin_datos"}


def test_forgetting_risk_low_when_nothing_due():
    _make_user()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO vocab_progress (user_id, vocab_key, due_at) VALUES (?, ?, ?)",
            ("u1", "greetings.hello", (datetime.now(UTC) + timedelta(days=5)).isoformat()),
        )
    result = predictions.forgetting_risk("u1")
    assert result["due_count"] == 0
    assert result["risk_level"] == "bajo"


def test_forgetting_risk_high_when_many_overdue_items():
    _make_user()
    with db.cursor() as cur:
        for i in range(4):
            cur.execute(
                "INSERT INTO vocab_progress (user_id, vocab_key, due_at) VALUES (?, ?, ?)",
                ("u1", f"word.{i}", (datetime.now(UTC) - timedelta(days=5)).isoformat()),
            )
    result = predictions.forgetting_risk("u1")
    assert result["due_count"] == 4
    assert result["risk_level"] == "alto"
    assert result["overdue_days_max"] >= 5


def test_dropout_risk_no_data_for_never_active_user():
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO users
               (id, display_name, native_lang, target_lang, level, interests, xp, streak_days,
                gems, streak_freezes, created_at, last_active_date)
               VALUES ('u1', 'Test', 'en', 'es', 'A1', '[]', 0, 0, 0, 0, ?, '')""",
            (db.now_iso(),),
        )
    result = predictions.dropout_risk("u1")
    assert result["risk_level"] == "sin_datos"


def test_dropout_risk_low_when_active_today():
    _make_user()  # last_active_date defaults to today
    with db.cursor() as cur:
        cur.execute("UPDATE users SET streak_days=5 WHERE id='u1'")
    result = predictions.dropout_risk("u1")
    assert result["days_since_last_active"] == 0
    assert result["risk_level"] == "bajo"


def test_dropout_risk_high_after_long_gap_and_broken_streak():
    _make_user()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE users SET last_active_date=?, streak_days=0 WHERE id='u1'",
            ((datetime.fromisoformat(db.today_str()) - timedelta(days=10)).date().isoformat(),),
        )
    result = predictions.dropout_risk("u1")
    assert result["days_since_last_active"] == 10
    assert result["risk_level"] == "alto"


def test_time_to_mastery_no_data_until_first_completion():
    result = predictions.time_to_mastery_estimate(db.now_iso(), completed_count=0, total_courses=10)
    assert result["estimated_days_remaining"] is None
    assert result["remaining_courses"] == 10


def test_time_to_mastery_already_done():
    result = predictions.time_to_mastery_estimate(db.now_iso(), completed_count=10, total_courses=10)
    assert result == {"remaining_courses": 0, "estimated_days_remaining": 0, "pace_courses_per_day": None}


def test_time_to_mastery_extrapolates_from_real_pace():
    enrolled_at = (datetime.fromisoformat(db.today_str()) - timedelta(days=10)).isoformat()
    result = predictions.time_to_mastery_estimate(enrolled_at, completed_count=5, total_courses=15)
    # pace = 5 courses / 10 days = 0.5/day; remaining 10 courses -> 20 days
    assert result["remaining_courses"] == 10
    assert result["estimated_days_remaining"] == 20
    assert result["pace_courses_per_day"] == 0.5


# ── Learning style (inferred, never asked) ───────────────────────────────


def _log_conversation_turns(user_id: str, n: int):
    with db.cursor() as cur:
        for _ in range(n):
            cur.execute(
                "INSERT INTO conversation_log (user_id, role, content, created_at) VALUES (?, 'user', 'hola', ?)",
                (user_id, db.now_iso()),
            )


def _log_lessons(user_id: str, n: int, score: float = 0.9):
    with db.cursor() as cur:
        for _ in range(n):
            cur.execute(
                "INSERT INTO lesson_history (user_id, unit_id, score, completed_at) VALUES (?, 'u0', ?, ?)",
                (user_id, score, db.now_iso()),
            )


def test_learning_style_sin_datos_below_activity_floor():
    _make_user()
    _log_conversation_turns("u1", 1)
    result = learning_style.infer_learning_style("u1")
    assert result["style"] == "sin_datos"


def test_learning_style_conversacional_when_chat_dominates():
    _make_user()
    _log_conversation_turns("u1", 8)
    _log_lessons("u1", 1)
    result = learning_style.infer_learning_style("u1")
    assert result["style"] == "conversacional"


def test_learning_style_estructurado_when_written_dominates():
    _make_user()
    _log_conversation_turns("u1", 1)
    _log_lessons("u1", 8)
    result = learning_style.infer_learning_style("u1")
    assert result["style"] == "estructurado"


def test_learning_style_equilibrado_when_close():
    _make_user()
    _log_conversation_turns("u1", 5)
    _log_lessons("u1", 5)
    result = learning_style.infer_learning_style("u1")
    assert result["style"] == "equilibrado"


# ── Motivation signal (specific, non-generic) ────────────────────────────


def test_motivation_sin_datos_with_too_few_lessons():
    _make_user()
    _log_lessons("u1", 2, score=0.9)
    result = motivation.detect_signal("u1")
    assert result["signal"] == "sin_datos"
    assert result["message"] == ""


def test_motivation_detects_frustracion_on_repeated_low_scores():
    _make_user()
    for score in [0.2, 0.3, 0.1]:
        _log_lessons("u1", 1, score=score)
    result = motivation.detect_signal("u1")
    assert result["signal"] == "frustracion"
    assert result["message"] != ""


def test_motivation_detects_buen_momentum_on_strong_scores():
    _make_user()
    for score in [0.9, 0.95, 1.0]:
        _log_lessons("u1", 1, score=score)
    result = motivation.detect_signal("u1")
    assert result["signal"] == "buen_momentum"
    assert result["message"] != ""


def test_motivation_detects_estancado_on_flat_scores():
    _make_user()
    for score in [0.6, 0.65, 0.62, 0.61]:
        _log_lessons("u1", 1, score=score)
    result = motivation.detect_signal("u1")
    assert result["signal"] == "estancado"
