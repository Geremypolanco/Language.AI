import pytest
from fastapi.testclient import TestClient

from backend import academy, db, mastery
from backend.main import app
from test_api import _onboard

_STRONG_METRICS = {"academic_depth_score": 97, "structural_logical_fallacies": []}
_WEAK_METRICS = {"academic_depth_score": 60, "structural_logical_fallacies": ["hasty generalization"]}


def _course_id(field_id="computer-science", level="ASSOCIATE", order=0):
    return f"{field_id}:{level}:{order}"


def test_evaluate_academic_promotion_rejects_malformed_course_id():
    with pytest.raises(ValueError):
        mastery.evaluate_academic_promotion("user1", "not-a-real-course-id", _STRONG_METRICS)


def test_no_fast_track_before_the_streak_is_complete():
    course_id = _course_id()
    result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)
    assert result["streak_length"] == 1
    assert result["course_fast_tracked"] is False

    result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)
    assert result["streak_length"] == 2
    assert result["course_fast_tracked"] is False


def test_fast_tracks_the_course_after_a_genuine_three_turn_streak():
    course_id = _course_id()
    for _ in range(mastery.MASTERY_STREAK_LENGTH):
        result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)

    assert result["streak_length"] == mastery.MASTERY_STREAK_LENGTH
    assert result["course_fast_tracked"] is True

    with db.cursor() as cur:
        cur.execute(
            "SELECT completed_at FROM academy_course_progress WHERE user_id=? AND course_id=?",
            ("user1", course_id),
        )
        assert cur.fetchone() is not None


def test_a_single_weak_turn_resets_the_streak_and_blocks_fast_tracking():
    course_id = _course_id()
    mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)
    mastery.evaluate_academic_promotion("user1", course_id, _WEAK_METRICS)
    result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)
    result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)
    # Only 2 strong turns since the weak one broke the window — still short
    # of a genuine 3-in-a-row streak.
    assert result["course_fast_tracked"] is False


def test_never_auto_jumps_degree_levels_even_after_finishing_every_course():
    """The whole point of this module: finishing every ASSOCIATE course only
    ever produces a recommendation, never a silent level change — and this
    app has no code path anywhere that mutates a user's enrolled `level`
    based on academic_depth_score."""
    field = academy.all_fields()[0]
    total_courses = 12  # AcademicLevel.ASSOCIATE.course_count
    last_result = None
    for order in range(total_courses):
        course_id = _course_id(field.id, "ASSOCIATE", order)
        for _ in range(mastery.MASTERY_STREAK_LENGTH):
            last_result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)

    assert last_result["level_complete_recommendation"] is True
    assert last_result["recommended_next_level"] == "BACHELOR"

    with db.cursor() as cur:
        cur.execute("SELECT level FROM academy_enrollment WHERE user_id=?", ("user1",))
        # No enrollment row was ever written by evaluate_academic_promotion —
        # it never touches academy_enrollment at all.
        assert cur.fetchone() is None


def test_doctorate_has_no_next_level_to_recommend():
    field = academy.all_fields()[0]
    last_result = None
    for order in range(8):  # AcademicLevel.DOCTORATE.course_count
        course_id = _course_id(field.id, "DOCTORATE", order)
        for _ in range(mastery.MASTERY_STREAK_LENGTH):
            last_result = mastery.evaluate_academic_promotion("user1", course_id, _STRONG_METRICS)

    assert last_result["level_complete_recommendation"] is False
    assert last_result["recommended_next_level"] is None


def test_ask_faculty_endpoint_grades_the_turn_and_reports_promotion_state(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_conversation_reply(system_prompt, history, temperature=0.8):
        assert "ACADEMIC GRADING" in system_prompt
        return {
            "spoken_response": "Buena pregunta — vamos a revisar la complejidad de ese algoritmo.",
            "critique_metrics": dict(_STRONG_METRICS),
        }

    monkeypatch.setattr(hf_client_module.hf_client, "conversation_reply", fake_conversation_reply)

    with TestClient(app) as client:
        user = _onboard(client, email="faculty-ask@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = _course_id(field_id, "ASSOCIATE", 0)

        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/ask", json={"question": "Why is this NP-hard?"})
        assert res.status_code == 200
        data = res.json()
        assert data["critique_metrics"]["academic_depth_score"] == 97
        assert data["promotion"]["course_fast_tracked"] is False
        assert data["promotion"]["streak_length"] == 1

        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/ask", json={"question": "And this one?"})
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/ask", json={"question": "One more?"})
        assert res.status_code == 200


def test_ask_faculty_emits_a_student_turn_telemetry_event(monkeypatch, caplog):
    import json as json_module

    from backend import hf_client as hf_client_module

    async def fake_conversation_reply(system_prompt, history, temperature=0.8):
        return {"spoken_response": "Buena pregunta.", "critique_metrics": dict(_STRONG_METRICS)}

    monkeypatch.setattr(hf_client_module.hf_client, "conversation_reply", fake_conversation_reply)

    with TestClient(app) as client:
        user = _onboard(client, email="faculty-telemetry@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = _course_id(field_id, "ASSOCIATE", 0)

        with caplog.at_level("INFO", logger="lingua.telemetry"):
            res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/ask", json={"question": "Why?"})
        assert res.status_code == 200

    student_turn_records = [r for r in caplog.records if r.name == "lingua.telemetry"]
    assert len(student_turn_records) == 1
    payload = json_module.loads(student_turn_records[0].message)
    assert payload["event"] == "student_turn"
    assert payload["duration_ms"] >= 0
    assert payload["circuit_breaker_state"] is False
    # ask_faculty doesn't call text_to_speech itself — no voice tier claim
    # for a synthesis step that never ran in this transaction.
    assert payload["voice_tier_utilized"] == "none"


def test_ask_faculty_requires_enrollment():
    with TestClient(app) as client:
        user = _onboard(client, email="faculty-ask-noenroll@example.com")
        res = client.post(
            f"/api/academy/{user['id']}/courses/computer-science:ASSOCIATE:0/ask",
            json={"question": "hello"},
        )
        assert res.status_code == 404
