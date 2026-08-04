import asyncio

from backend import db
from backend.learning_engine import (
    achievements,
    analytics,
    competency,
    concept_review,
    grading,
    knowledge_graph,
    portfolio,
    recommendations,
)


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


def test_get_portfolio_empty_for_new_user():
    _make_user()
    result = portfolio.get_portfolio("u1")
    assert result == {"assignments": [], "scenarios": [], "completed_courses": []}
