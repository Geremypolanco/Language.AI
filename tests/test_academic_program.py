from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import academic_program, academy, db
from backend.main import app
from test_api import _onboard


def _course_id(field_id, order):
    return f"{field_id}:BACHELOR:{order}"


# ── Pure grading math ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "percentage,expected",
    [
        (100, "A+"), (97, "A+"), (96.9, "A"), (93, "A"), (92.9, "A-"),
        (90, "A-"), (89.9, "B+"), (83, "B"), (79.9, "C+"), (73, "C"),
        (69.9, "D+"), (60, "D-"), (59.9, "F"), (0, "F"),
    ],
)
def test_letter_grade_boundaries(percentage, expected):
    assert academic_program.letter_grade_for(percentage) == expected


def test_gpa_points_for_every_letter_the_scale_produces():
    for percentage in range(0, 101):
        letter = academic_program.letter_grade_for(percentage)
        assert isinstance(academic_program.gpa_points_for(letter), float)


def test_compute_final_percentage_weights_20_30_50():
    result = academic_program.compute_final_percentage(quiz_score=100, midterm_score=100, final_score=0)
    assert result == pytest.approx(50.0)  # only the 50%-weighted final was 0
    result2 = academic_program.compute_final_percentage(quiz_score=80, midterm_score=80, final_score=80)
    assert result2 == pytest.approx(80.0)


def test_compute_final_percentage_is_none_until_all_three_present():
    assert academic_program.compute_final_percentage(90, 90, None) is None
    assert academic_program.compute_final_percentage(None, None, None) is None
    assert academic_program.compute_final_percentage(90, 90, 90) == pytest.approx(90.0)


@pytest.mark.parametrize(
    "credits,expected",
    [(0, "Freshman"), (30, "Freshman"), (31, "Sophomore"), (60, "Sophomore"), (61, "Junior"), (90, "Junior"), (91, "Senior"), (200, "Senior")],
)
def test_class_standing_boundaries(credits, expected):
    assert academic_program.class_standing_for(credits) == expected


def test_build_program_structure_sums_to_120_credits_across_8_semesters():
    field = academy.all_fields()[0]
    structure = academic_program.build_program_structure(field.id)
    assert len(structure) == 24
    assert sum(c.credits for c in structure) == 120
    assert {c.semester for c in structure} == set(range(1, 9))
    for semester in range(1, 9):
        assert sum(1 for c in structure if c.semester == semester) == 3


# ── DB-backed behavior ───────────────────────────────────────────────────


def test_is_course_unlocked_semester_1_is_always_unlocked():
    field = academy.all_fields()[0]
    assert academic_program.is_course_unlocked("some-user", _course_id(field.id, 0)) is True


def test_is_course_unlocked_requires_prior_semester_fully_passed():
    field = academy.all_fields()[0]
    user_id = "user-lock-test"
    semester_2_course = _course_id(field.id, 3)  # order 3 = first course of semester 2
    assert academic_program.is_course_unlocked(user_id, semester_2_course) is False

    # Pass only 2 of the 3 semester-1 courses — still locked.
    academic_program.record_grade_component(user_id, _course_id(field.id, 0), 100, 100, 100)
    academic_program.record_grade_component(user_id, _course_id(field.id, 1), 100, 100, 100)
    assert academic_program.is_course_unlocked(user_id, semester_2_course) is False

    # Pass the third — now unlocked.
    academic_program.record_grade_component(user_id, _course_id(field.id, 2), 100, 100, 100)
    assert academic_program.is_course_unlocked(user_id, semester_2_course) is True


def test_record_grade_component_merges_partial_submissions():
    field = academy.all_fields()[0]
    course_id = _course_id(field.id, 0)
    user_id = "user-partial"

    result = academic_program.record_grade_component(user_id, course_id, quiz_score=90)
    assert result["final_percentage"] is None
    assert result["passed"] is False

    result = academic_program.record_grade_component(user_id, course_id, midterm_score=80)
    assert result["quiz_score"] == 90
    assert result["final_percentage"] is None

    result = academic_program.record_grade_component(user_id, course_id, final_score=70)
    assert result["final_percentage"] == pytest.approx(90 * 0.2 + 80 * 0.3 + 70 * 0.5)
    assert result["letter_grade"] == academic_program.letter_grade_for(result["final_percentage"])
    assert result["passed"] is True


def test_record_grade_component_below_passing_is_not_marked_passed():
    field = academy.all_fields()[0]
    course_id = _course_id(field.id, 0)
    result = academic_program.record_grade_component("user-fail", course_id, 50, 50, 50)
    assert result["final_percentage"] == pytest.approx(50.0)
    assert result["passed"] is False


def test_compute_program_progress_tracks_credits_and_gpa():
    field = academy.all_fields()[0]
    user_id = "user-progress"
    academic_program.record_grade_component(user_id, _course_id(field.id, 0), 100, 100, 100)  # A+, 4.0
    academic_program.record_grade_component(user_id, _course_id(field.id, 1), 50, 50, 50)  # fails

    progress = academic_program.compute_program_progress(user_id, field.id)
    assert progress["credits_earned"] == 5  # one 5-credit course passed
    assert progress["total_credits"] == 120
    assert progress["courses_passed"] == 1
    assert progress["class_standing"] == "Freshman"
    assert progress["gpa"] == pytest.approx(4.0)


def test_estimate_graduation_reports_insufficient_data_with_fewer_than_two_completions():
    field = academy.all_fields()[0]
    user_id = "user-eta-nodata"
    result = academic_program.estimate_graduation(user_id, field.id)
    assert result["has_enough_data"] is False
    assert result["humanized"] is None

    academic_program.record_grade_component(user_id, _course_id(field.id, 0), 100, 100, 100)
    result = academic_program.estimate_graduation(user_id, field.id)
    assert result["has_enough_data"] is False


def test_estimate_graduation_computes_velocity_from_real_timestamps():
    field = academy.all_fields()[0]
    user_id = "user-eta-velocity"
    course_a, course_b = _course_id(field.id, 0), _course_id(field.id, 1)
    academic_program.record_grade_component(user_id, course_a, 100, 100, 100)
    academic_program.record_grade_component(user_id, course_b, 100, 100, 100)

    now = datetime.now(UTC)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE academy_course_progress SET completed_at=? WHERE user_id=? AND course_id=?",
            ((now - timedelta(days=60)).isoformat(), user_id, course_a),
        )
        cur.execute(
            "UPDATE academy_course_progress SET completed_at=? WHERE user_id=? AND course_id=?",
            (now.isoformat(), user_id, course_b),
        )

    result = academic_program.estimate_graduation(user_id, field.id)
    assert result["has_enough_data"] is True
    # 10 credits earned over 60 days ≈ 30.44/60*10 ≈ 5.07 credits/month
    assert result["velocity_credits_per_month"] == pytest.approx(5.07, abs=0.1)
    assert result["months_remaining"] > 0
    assert "graduarte" in result["humanized"]


def test_get_next_step_advances_when_nothing_is_failed():
    field = academy.all_fields()[0]
    result = academic_program.get_next_step("user-nextstep-fresh", field.id)
    assert result["action"] == "advance"
    assert result["course_id"] == _course_id(field.id, 0)


def test_get_next_step_remediates_a_failed_course_before_advancing():
    field = academy.all_fields()[0]
    user_id = "user-nextstep-fail"
    academic_program.record_grade_component(user_id, _course_id(field.id, 0), 40, 40, 40)
    result = academic_program.get_next_step(user_id, field.id)
    assert result["action"] == "remediate"
    assert result["course_id"] == _course_id(field.id, 0)
    assert result["final_percentage"] == pytest.approx(40.0)


def test_get_next_step_reports_graduated_when_every_course_passed():
    field = academy.all_fields()[0]
    user_id = "user-graduated"
    for order in range(24):
        academic_program.record_grade_component(user_id, _course_id(field.id, order), 100, 100, 100)
    result = academic_program.get_next_step(user_id, field.id)
    assert result["action"] == "graduated"


# ── API layer ────────────────────────────────────────────────────────────


def test_submit_grade_endpoint_rejects_out_of_range_scores():
    with TestClient(app) as client:
        user = _onboard(client, email="grade1@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "BACHELOR"})
        course_id = _course_id(field_id, 0)
        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/grade", json={"quiz_score": 150})
        assert res.status_code == 422


def test_submit_grade_endpoint_rejects_non_bachelor_courses():
    with TestClient(app) as client:
        user = _onboard(client, email="grade2@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = f"{field_id}:ASSOCIATE:0"
        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/grade", json={"quiz_score": 90})
        assert res.status_code == 422


def test_submit_grade_endpoint_blocks_locked_courses():
    with TestClient(app) as client:
        user = _onboard(client, email="grade3@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "BACHELOR"})
        semester_2_course = _course_id(field_id, 3)
        res = client.post(f"/api/academy/{user['id']}/courses/{semester_2_course}/grade", json={"quiz_score": 90})
        assert res.status_code == 403


def test_submit_grade_endpoint_accepts_and_computes():
    with TestClient(app) as client:
        user = _onboard(client, email="grade4@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "BACHELOR"})
        course_id = _course_id(field_id, 0)
        res = client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/grade",
            json={"quiz_score": 90, "midterm_score": 90, "final_score": 90},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] is True
        assert data["letter_grade"] == "A-"


def test_program_progress_and_eta_and_next_step_endpoints():
    with TestClient(app) as client:
        user = _onboard(client, email="grade5@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "BACHELOR"})

        progress = client.get(f"/api/academy/{user['id']}/program/{field_id}/progress")
        assert progress.status_code == 200
        assert progress.json()["total_credits"] == 120

        eta = client.get(f"/api/academy/{user['id']}/program/{field_id}/graduation-eta")
        assert eta.status_code == 200
        assert eta.json()["has_enough_data"] is False

        next_step = client.get(f"/api/academy/{user['id']}/program/{field_id}/next-step")
        assert next_step.status_code == 200
        assert next_step.json()["action"] == "advance"
