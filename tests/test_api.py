from fastapi.testclient import TestClient

from backend.main import app
from conftest import dev_login


def _onboard(client, email="ada@example.com"):
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={
            "display_name": "Ada",
            "native_lang": "English",
            "target_lang": "Spanish",
            "level": "A1",
            "interests": ["music"],
        },
    )
    assert res.status_code == 200
    return res.json()


def test_full_onboarding_lesson_and_progress_flow():
    with TestClient(app) as client:
        user = _onboard(client)
        user_id = user["id"]
        assert user["xp"] == 0
        assert user["daily_goal_minutes"] == 15
        assert "email" not in user  # not part of the public UserProfile model

        path_res = client.get(f"/api/lessons/{user_id}/path")
        assert path_res.status_code == 200
        units = path_res.json()
        # Nothing is ever locked — the learner decides what to practice first.
        assert all(u["state"] in ("available", "mastered") for u in units)
        a1_units = [u for u in units if u["level"] == "A1"]

        first_unit_id = a1_units[0]["id"]
        lesson_res = client.get(f"/api/lessons/{user_id}/unit/{first_unit_id}")
        assert lesson_res.status_code == 200
        exercises = lesson_res.json()
        assert len(exercises) > 0
        assert exercises[0]["vocab_key"]

        for ex in exercises:
            answer_res = client.post(
                f"/api/lessons/{user_id}/answer",
                json={"vocab_key": ex["vocab_key"], "correct": True, "attempts_before_correct": 0},
            )
            assert answer_res.status_code == 200

        complete_res = client.post(
            f"/api/lessons/{user_id}/complete",
            json={"unit_id": first_unit_id, "score": 1.0},
        )
        assert complete_res.status_code == 200
        complete = complete_res.json()
        assert complete["xp_gained"] == 30
        assert complete["mastered"] is True

        progress_res = client.get(f"/api/progress/{user_id}")
        assert progress_res.status_code == 200
        progress = progress_res.json()
        assert progress["xp"] == 30
        assert progress["units_mastered"] == 1


def test_first_ever_lesson_starts_the_streak_at_one():
    """Regression: a freshly-onboarded user's `last_active_date` must NOT be
    pre-seeded to today, or record_lesson_result's `last_active_date != today`
    check never fires on their actual first day of activity and the streak
    stays stuck at 0 instead of becoming 1."""
    with TestClient(app) as client:
        user = _onboard(client, email="streak@example.com")
        assert user["streak_days"] == 0

        path = client.get(f"/api/lessons/{user['id']}/path").json()
        first_unit_id = next(u["id"] for u in path if u["level"] == "A1")
        complete = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": first_unit_id, "score": 1.0},
        ).json()

        assert complete["streak_days"] == 1


def test_any_unit_is_reachable_regardless_of_level():
    """The learner decides what to master first — a C2 unit must be just as
    reachable as an A1 one from day one, no level gate."""
    with TestClient(app) as client:
        user = _onboard(client)
        advanced_unit_id = "C2-0"
        res = client.get(f"/api/lessons/{user['id']}/unit/{advanced_unit_id}")
        assert res.status_code == 200
        assert len(res.json()) > 0


def test_no_session_returns_401():
    with TestClient(app) as client:
        res = client.get("/api/users/does-not-exist")
        assert res.status_code == 401


def test_accessing_someone_elses_profile_returns_403():
    with TestClient(app) as client:
        user = _onboard(client)
        res = client.get(f"/api/users/{user['id']}not-mine")
        assert res.status_code == 403


def test_returning_user_reuses_profile_via_dev_login():
    with TestClient(app) as client:
        first = _onboard(client, email="returning@example.com")
        client.post("/auth/logout")
        second_res = client.get("/api/session")
        assert second_res.json()["authenticated"] is False

        dev_login(client, "returning@example.com")
        session_res = client.get("/api/session")
        session = session_res.json()
        assert session["authenticated"] is True
        assert session["user_id"] == first["id"]


def test_creating_profile_without_login_is_rejected():
    with TestClient(app) as client:
        res = client.post(
            "/api/users",
            json={"display_name": "Ghost", "native_lang": "English", "target_lang": "Spanish", "level": "A1"},
        )
        assert res.status_code == 401


def test_dashboard_reflects_completed_lesson():
    with TestClient(app) as client:
        user = _onboard(client, email="dash@example.com")
        user_id = user["id"]

        path = client.get(f"/api/lessons/{user_id}/path").json()
        first_unit_id = next(u["id"] for u in path if u["level"] == "A1")
        client.post(f"/api/lessons/{user_id}/complete", json={"unit_id": first_unit_id, "score": 1.0})

        res = client.get(f"/api/progress/{user_id}/dashboard")
        assert res.status_code == 200
        data = res.json()

        assert data["level"] == "A1"
        assert data["next_level"] == "A2"
        assert data["units_mastered_current_level"] == 1
        assert data["units_total_current_level"] > 0

        a1_entry = next(m for m in data["mastery_by_level"] if m["level"] == "A1")
        assert a1_entry["mastered"] == 1
        levels_in_order = [m["level"] for m in data["mastery_by_level"]]
        assert levels_in_order == ["A1", "A2", "B1", "B2", "C1", "C2", "NATIVE"]

        assert len(data["activity"]) == 14
        assert data["activity"][-1]["lessons_completed"] == 1  # today, last entry

        assert len(data["recent_lessons"]) == 1
        assert data["recent_lessons"][0]["unit_id"] == first_unit_id
        assert data["recent_lessons"][0]["score"] == 1.0


def test_dashboard_requires_ownership():
    with TestClient(app) as client:
        user = _onboard(client, email="dash2@example.com")
        res = client.get(f"/api/progress/{user['id']}not-mine/dashboard")
        assert res.status_code == 403


def test_dashboard_includes_gems_and_leaderboard():
    with TestClient(app) as client:
        user = _onboard(client, email="gems@example.com")
        user_id = user["id"]
        path = client.get(f"/api/lessons/{user_id}/path").json()
        first_unit_id = next(u["id"] for u in path if u["level"] == "A1")
        client.post(f"/api/lessons/{user_id}/complete", json={"unit_id": first_unit_id, "score": 1.0})

        data = client.get(f"/api/progress/{user_id}/dashboard").json()
        assert data["gems"] == 10
        assert data["streak_freezes"] == 0
        assert data["your_rank"] == 1
        assert data["your_weekly_xp"] == 30
        assert data["leaderboard"][0]["is_you"] is True


def test_shop_buy_streak_freeze_requires_enough_gems():
    with TestClient(app) as client:
        user = _onboard(client, email="shop1@example.com")
        res = client.post(f"/api/shop/{user['id']}/streak-freeze")
        assert res.status_code == 400  # 0 gems on a brand-new account


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        body = res.json()
        assert "hf_configured" in body
        assert "google_configured" in body


def test_placement_test_requires_pending_signin():
    with TestClient(app) as client:
        res = client.post(
            "/api/placement",
            json={"native_lang": "English", "target_lang": "Spanish", "history": []},
        )
        assert res.status_code == 401


def test_placement_test_starts_at_a2_and_converges_after_six_questions():
    with TestClient(app) as client:
        dev_login(client, "placement1@example.com")
        res = client.post(
            "/api/placement",
            json={"native_lang": "English", "target_lang": "Spanish", "history": []},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["done"] is False
        assert body["level"] == "A2"
        assert body["exercise"]["vocab_key"]

        history = [{"level": "A2", "correct": True}] * 6
        res = client.post(
            "/api/placement",
            json={"native_lang": "English", "target_lang": "Spanish", "history": history},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["done"] is True
        assert body["recommended_level"] is not None


def test_placement_test_moves_down_a_level_after_a_wrong_answer():
    with TestClient(app) as client:
        dev_login(client, "placement2@example.com")
        history = [{"level": "A2", "correct": False}]
        res = client.post(
            "/api/placement",
            json={"native_lang": "English", "target_lang": "Spanish", "history": history},
        )
        assert res.status_code == 200
        assert res.json()["level"] == "A1"


def test_tutor_reply_requires_signin():
    with TestClient(app) as client:
        res = client.post(
            "/api/content/tutor-reply",
            json={
                "target_lang": "Spanish",
                "native_lang": "English",
                "level": "A2",
                "prompt": "What did you do today?",
                "user_answer": "Fui al parque.",
            },
        )
        assert res.status_code == 401


def test_tutor_reply_gives_a_demo_mode_reply_when_signed_in():
    with TestClient(app) as client:
        user = _onboard(client, email="tutorreply@example.com")
        res = client.post(
            "/api/content/tutor-reply",
            json={
                "target_lang": user["target_lang"],
                "native_lang": user["native_lang"],
                "level": user["level"],
                "interests": user["interests"],
                "prompt": "What did you do today?",
                "user_answer": "Fui al parque.",
            },
        )
        assert res.status_code == 200
        assert res.json()["reply"]


def test_daily_goal_minutes_is_user_editable_not_a_cap():
    with TestClient(app) as client:
        user = _onboard(client, email="goal@example.com")
        assert user["daily_goal_minutes"] == 15

        res = client.patch(f"/api/users/{user['id']}", json={"daily_goal_minutes": 45})
        assert res.status_code == 200
        assert res.json()["daily_goal_minutes"] == 45


def test_practice_session_generates_exercises_of_one_type_and_completes_normally():
    with TestClient(app) as client:
        user = _onboard(client, email="practice@example.com")
        res = client.post(
            f"/api/lessons/{user['id']}/practice",
            json={"exercise_type": "listen_type", "level": "A1"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["unit_id"] == "practice-listen_type-A1"
        assert len(body["exercises"]) == 5
        assert all(ex["type"] == "listen_type" for ex in body["exercises"])

        complete_res = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": body["unit_id"], "score": 1.0, "elapsed_seconds": 120},
        )
        assert complete_res.status_code == 200
        assert complete_res.json()["xp_gained"] == 30

        progress = client.get(f"/api/progress/{user['id']}").json()
        assert progress["today_minutes"] == 2


def test_library_catalog_has_500_plus_titles_across_every_level():
    with TestClient(app) as client:
        user = _onboard(client, email="library1@example.com")
        res = client.get(f"/api/library/{user['id']}/catalog", params={"limit": 100})
        assert res.status_code == 200
        assert len(res.json()) == 100  # paginated — full catalog is 500+, checked below

        from backend.library import CATALOG

        assert len(CATALOG) >= 500
        assert {b.level.value for b in CATALOG} == {"A1", "A2", "B1", "B2", "C1", "C2", "NATIVE"}


def test_library_catalog_filters_by_level_and_genre():
    with TestClient(app) as client:
        user = _onboard(client, email="library2@example.com")
        res = client.get(f"/api/library/{user['id']}/catalog", params={"level": "A1", "genre": "adventure", "limit": 100})
        assert res.status_code == 200
        books = res.json()
        assert len(books) > 0
        assert all(b["level"] == "A1" and b["genre"] == "adventure" for b in books)


def test_library_book_content_generates_demo_fallback_without_hf_token():
    with TestClient(app) as client:
        user = _onboard(client, email="library3@example.com")
        catalog_res = client.get(f"/api/library/{user['id']}/catalog", params={"limit": 1})
        book_id = catalog_res.json()[0]["id"]

        res = client.get(f"/api/library/{user['id']}/books/{book_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == book_id
        assert "modo demo" in body["content"].lower()


def test_library_book_not_found_returns_404():
    with TestClient(app) as client:
        user = _onboard(client, email="library4@example.com")
        res = client.get(f"/api/library/{user['id']}/books/does-not-exist")
        assert res.status_code == 404


def test_library_genres_endpoint_lists_all_genres():
    with TestClient(app) as client:
        res = client.get("/api/library/genres")
        assert res.status_code == 200
        assert len(res.json()) == 10


def test_recommendations_gives_demo_mode_suggestions_without_hf_token():
    with TestClient(app) as client:
        _onboard(client, email="recs@example.com")
        res = client.post(
            "/api/content/recommendations",
            json={"target_lang": "Spanish", "level": "A2", "interests": ["music"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body) > 0
        assert all({"kind", "title", "creator", "reason"} <= item.keys() for item in body)
