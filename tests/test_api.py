from fastapi.testclient import TestClient

from backend.academy_library.storage import FileSystemAcademyStore
from backend.main import app
from backend.models import AcademicField
from backend.routers import academy as academy_router
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

        # Knowledge heatmap: real per-topic mastery, not the old Math.random() stub.
        assert len(data["topic_mastery"]) == len(path)
        completed_cell = next(c for c in data["topic_mastery"] if c["topic"] == next(u["topic"] for u in path if u["id"] == first_unit_id))
        assert completed_cell["level"] == 4  # score 1.0 -> top bucket
        untouched_cell = next(c for c in data["topic_mastery"] if c["topic"] != completed_cell["topic"])
        assert untouched_cell["level"] == 0


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


def test_image_endpoint_falls_back_to_503_when_no_image_source_configured():
    # Neither GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX nor HF_TOKEN are set in tests —
    # confirms the Google-image-search-first, AI-generation-fallback chain
    # in the /api/content/image route degrades to a clear error instead of
    # a broken/empty response when nothing is configured.
    with TestClient(app) as client:
        _onboard(client, email="imagefallback@example.com")
        res = client.post("/api/content/image", json={"prompt": "a red apple"})
        assert res.status_code == 503


def test_image_gallery_returns_same_origin_item_urls_not_external_ones():
    # Regression test: this endpoint used to return raw image.pollinations.ai
    # URLs straight to the client (an AI generator, not a real image search,
    # despite being advertised as one) which the CSP's img-src also didn't
    # allowlist for a while. It should return same-origin URLs that this
    # app itself serves via /image-gallery-item, backed by the same real
    # search chain as /api/content/image.
    with TestClient(app) as client:
        _onboard(client, email="gallery@example.com")
        res = client.post("/api/content/image-gallery", json={"query": "manzana", "limit": 3})
        assert res.status_code == 200
        urls = res.json()
        assert len(urls) == 3
        for url in urls:
            assert url.startswith("/api/content/image-gallery-item?")
            assert "pollinations" not in url


def test_image_gallery_item_falls_back_to_503_when_no_image_source_configured():
    with TestClient(app) as client:
        _onboard(client, email="galleryfallback@example.com")
        res = client.get("/api/content/image-gallery-item", params={"query": "manzana", "index": 0, "limit": 4})
        assert res.status_code == 503


def test_daily_news_endpoint_degrades_gracefully_when_ai_is_unavailable():
    # Regression test: get_daily_news referenced get_user_by_id_or_404
    # without importing it (NameError on every call), and separately its
    # try/except only wrapped the JSON-parsing step, not the hf_client.chat
    # call itself — so when every AI provider is unavailable (as in tests),
    # the endpoint 500'd instead of returning its own intended fallback.
    with TestClient(app) as client:
        _onboard(client, email="newsfallback@example.com")
        res = client.get("/api/content/news")
        assert res.status_code == 200
        assert res.json()["news"][0]["title"] == "News Unavailable"


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
        # Each of the 5 requested listen_type exercises now has its own
        # preceding vocab_intro teaching card (see
        # hf_client._with_teaching_intros) — 10 total, alternating.
        assert len(body["exercises"]) == 10
        assert [ex["type"] for ex in body["exercises"]] == ["vocab_intro", "listen_type"] * 5

        complete_res = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": body["unit_id"], "score": 1.0, "elapsed_seconds": 120},
        )
        assert complete_res.status_code == 200
        assert complete_res.json()["xp_gained"] == 30

        progress = client.get(f"/api/progress/{user['id']}").json()
        assert progress["today_minutes"] == 2


def test_review_session_is_empty_when_nothing_is_due():
    with TestClient(app) as client:
        user = _onboard(client, email="review-empty@example.com")
        res = client.get(f"/api/lessons/{user['id']}/review")
        assert res.status_code == 200
        assert res.json()["exercises"] == []


def test_review_session_serves_and_reschedules_a_due_item():
    from backend import db

    with TestClient(app) as client:
        user = _onboard(client, email="review@example.com")

        # Grade an exercise once, capturing its content snapshot — same as
        # ExercisePlayer does on every graded answer.
        answer_res = client.post(
            f"/api/lessons/{user['id']}/answer",
            json={
                "vocab_key": "greetings.hello",
                "correct": True,
                "target_text": "Hola",
                "native_text": "Hello",
                "unit_id": "A1-0",
            },
        )
        assert answer_res.status_code == 200

        # Force it due right now — a fresh correct answer schedules review a
        # day out, and this test isn't about SM-2 timing, just the session.
        with db.cursor() as cur:
            cur.execute(
                "UPDATE vocab_progress SET due_at='2000-01-01T00:00:00+00:00' "
                "WHERE user_id=? AND vocab_key='greetings.hello'",
                (user["id"],),
            )

        review_res = client.get(f"/api/lessons/{user['id']}/review")
        assert review_res.status_code == 200
        body = review_res.json()
        assert body["unit_id"] == "practice-review"
        assert len(body["exercises"]) == 1
        exercise = body["exercises"][0]
        # No AI configured in tests (settings.testing) — the honest,
        # content-snapshot-based fallback is what's actually exercised here.
        assert exercise["vocab_key"] == "greetings.hello"
        assert exercise["target_text"] == "Hola"
        assert exercise["correct_answer"] == "Hello"

        # Grading the review answer must reschedule the same row further out.
        client.post(
            f"/api/lessons/{user['id']}/answer",
            json={"vocab_key": "greetings.hello", "correct": True},
        )
        with db.cursor() as cur:
            cur.execute(
                "SELECT due_at FROM vocab_progress WHERE user_id=? AND vocab_key='greetings.hello'",
                (user["id"],),
            )
            due_at = cur.fetchone()["due_at"]
        assert due_at > "2000-01-01"


def test_a1_free_practice_never_seeds_content_from_the_alphabet_unit(monkeypatch):
    # Regression: A1's first unit is "Alphabet & first sounds" (see
    # curriculum.py), and get_practice_exercises used to always build its
    # LessonRequest from units_for_level(level)[0] — which meant any A1
    # free-practice session (translate, listen, speak, free conversation...)
    # silently got the alphabet unit as its topic/context, forcing "teach
    # one letter at a time" instructions into requests that had nothing to
    # do with the alphabet.
    from backend.curriculum import ALPHABET_TOPIC
    from backend.routers import lessons as lessons_router

    seen_units = []
    original = lessons_router.hf_client.generate_exercises

    async def spy(req, mix_override=None):
        seen_units.append(req.unit.topic)
        return await original(req, mix_override)

    with TestClient(app) as client:
        # Onboarding schedules its own background exercise prefetch (see
        # users.py's _prefetch_units) — the spy is only installed after
        # onboarding completes so it observes just the /practice request
        # under test, not that unrelated prefetch.
        user = _onboard(client, email="practice-alphabet@example.com")
        monkeypatch.setattr(lessons_router.hf_client, "generate_exercises", spy)
        res = client.post(
            f"/api/lessons/{user['id']}/practice",
            json={"exercise_type": "free_conversation_prompt", "level": "A1"},
        )
        assert res.status_code == 200
        assert len(seen_units) == 1
        assert seen_units[0] != ALPHABET_TOPIC


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


def test_library_book_content_generates_offline_fallback_in_test_env():
    # AI calls run through Pollinations (free, keyless — always "configured"),
    # so settings.testing is what keeps the suite offline: chat() raises
    # immediately instead of attempting a real network request, and this
    # exercises that fallback path rather than a "missing token" state that
    # no longer exists.
    with TestClient(app) as client:
        user = _onboard(client, email="library3@example.com")
        catalog_res = client.get(f"/api/library/{user['id']}/catalog", params={"limit": 1})
        book_id = catalog_res.json()[0]["id"]

        res = client.get(f"/api/library/{user['id']}/books/{book_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == book_id
        assert "no se pudo generar" in body["content"].lower()


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


def test_academy_fields_lists_30_plus_fields_across_categories():
    with TestClient(app) as client:
        res = client.get("/api/academy/fields")
        assert res.status_code == 200
        fields = res.json()
        assert len(fields) >= 30
        assert len({f["category"] for f in fields}) >= 5


def test_academy_curriculum_requires_enrollment_first():
    with TestClient(app) as client:
        user = _onboard(client, email="academy1@example.com")
        res = client.get(f"/api/academy/{user['id']}/curriculum")
        assert res.status_code == 404


def test_academy_enroll_curriculum_course_and_complete_flow():
    with TestClient(app) as client:
        user = _onboard(client, email="academy2@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]

        enroll_res = client.post(
            f"/api/academy/{user['id']}/enroll",
            json={"field_id": field_id, "level": "ASSOCIATE"},
        )
        assert enroll_res.status_code == 200
        enrollment = enroll_res.json()
        assert enrollment["field_id"] == field_id
        assert enrollment["level"] == "ASSOCIATE"
        assert "no otorga" not in enrollment["level_label"].lower()  # label itself is short; disclaimer lives in the UI

        curriculum_res = client.get(f"/api/academy/{user['id']}/curriculum")
        assert curriculum_res.status_code == 200
        courses = curriculum_res.json()["courses"]
        assert len(courses) == 12  # ASSOCIATE.course_count
        course_id = courses[0]["id"]

        course_res = client.get(f"/api/academy/{user['id']}/courses/{course_id}")
        assert course_res.status_code == 200
        assert len(course_res.json()["modules"]) > 0

        complete_res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/complete")
        assert complete_res.status_code == 200
        progress = complete_res.json()
        assert progress["completed_course_ids"] == [course_id]
        assert progress["total_courses"] == 12

        # Completing again is idempotent, not double-counted.
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/complete")
        progress2 = client.get(f"/api/academy/{user['id']}/progress").json()
        assert progress2["completed_course_ids"] == [course_id]


def test_academy_re_enrolling_switches_field_and_level():
    with TestClient(app) as client:
        user = _onboard(client, email="academy3@example.com")
        fields = client.get("/api/academy/fields").json()

        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": fields[0]["id"], "level": "ASSOCIATE"})
        res = client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": fields[1]["id"], "level": "MASTER"})
        assert res.status_code == 200
        assert res.json()["field_id"] == fields[1]["id"]
        assert res.json()["level"] == "MASTER"

        progress = client.get(f"/api/academy/{user['id']}/progress").json()
        assert progress["enrollment"]["field_id"] == fields[1]["id"]
        assert progress["total_courses"] == 10  # MASTER.course_count


def test_academy_progress_with_no_enrollment_returns_null():
    with TestClient(app) as client:
        user = _onboard(client, email="academy4@example.com")
        res = client.get(f"/api/academy/{user['id']}/progress")
        assert res.status_code == 200
        assert res.json()["enrollment"] is None


def test_academy_enroll_requires_ownership():
    with TestClient(app) as client:
        user = _onboard(client, email="academy5@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        res = client.post(
            f"/api/academy/{user['id']}not-mine/enroll",
            json={"field_id": field_id, "level": "ASSOCIATE"},
        )
        assert res.status_code == 403


def test_academy_fields_include_tutor_name():
    with TestClient(app) as client:
        fields = client.get("/api/academy/fields").json()
        assert all(f["tutor_name"] for f in fields)
        assert len({f["tutor_name"] for f in fields}) == len(fields)  # every tutor name is unique


def test_academy_practice_scenario_and_feedback_demo_mode():
    with TestClient(app) as client:
        user = _onboard(client, email="academy6@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = client.get(f"/api/academy/{user['id']}/curriculum").json()["courses"][0]["id"]

        scenario_res = client.get(f"/api/academy/{user['id']}/courses/{course_id}/scenario")
        assert scenario_res.status_code == 200
        scenario = scenario_res.json()["scenario"]
        assert scenario

        feedback_res = client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/scenario/feedback",
            json={"scenario": scenario, "response": "Yo haría un diagnóstico paso a paso."},
        )
        assert feedback_res.status_code == 200
        assert feedback_res.json()["feedback"]


def test_academy_assignments_generate_and_submit_demo_mode():
    with TestClient(app) as client:
        user = _onboard(client, email="academy7@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = client.get(f"/api/academy/{user['id']}/curriculum").json()["courses"][0]["id"]

        assignments_res = client.get(f"/api/academy/{user['id']}/courses/{course_id}/assignments")
        assert assignments_res.status_code == 200
        assignments = assignments_res.json()
        assert assignments
        assert all(a["submitted"] is False for a in assignments)

        assignment_id = assignments[0]["id"]
        submit_res = client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/assignments/{assignment_id}/submit",
            json={"response": "Mi respuesta a la tarea."},
        )
        assert submit_res.status_code == 200
        assert "feedback" in submit_res.json()

        # submission status now persists
        assignments_after = client.get(f"/api/academy/{user['id']}/courses/{course_id}/assignments").json()
        submitted = next(a for a in assignments_after if a["id"] == assignment_id)
        assert submitted["submitted"] is True
        assert submitted["response"] == "Mi respuesta a la tarea."


def _seed_built_course(store, field_id, level, course_index=0):
    course_id = f"{field_id}:{level}:{course_index}"
    store.save_curriculum(field_id, level, "v1", {"courses": [{"title": "Curso Persistido", "description": "Una descripción real y completa."}]})
    store.set_latest_version(field_id, level, "v1")
    store.save_course_asset(field_id, level, "v1", course_id, "content", {"modules": [{"title": "Módulo persistido", "content": "contenido " * 20}]})
    store.save_course_asset(field_id, level, "v1", course_id, "glossary", {"terms": [{"term": "t1", "definition": "d1"}]})
    store.save_course_asset(field_id, level, "v1", course_id, "quiz", {"questions": [{"type": "open", "question": "q?", "rubric_note": "n"}]})
    store.save_course_asset(field_id, level, "v1", course_id, "exam", {"questions": [{"type": "open", "question": "q?", "rubric_note": "n"}], "rubric": "criteria"})
    store.save_course_asset(field_id, level, "v1", course_id, "assignments", [
        {"id": f"{course_id}:0", "type": "tarea", "title": "T", "instructions": "haz esto"},
        {"id": f"{course_id}:1", "type": "informe", "title": "I", "instructions": "escribe esto"},
        {"id": f"{course_id}:2", "type": "proyecto", "title": "P", "instructions": "construye esto"},
    ])
    store.save_course_asset(field_id, level, "v1", course_id, "scenario", "Un escenario práctico ya persistido para este curso.")
    return course_id


def test_academy_serves_pre_built_content_from_the_library_without_calling_hf_client(monkeypatch, tmp_path):
    async def explode(*args, **kwargs):
        raise AssertionError("hf_client.chat must not be called for a pre-built course")

    monkeypatch.setattr(academy_router.hf_client, "chat", explode)
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")

    with TestClient(app) as client:
        user = _onboard(client, email="academy-library1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        curriculum = client.get(f"/api/academy/{user['id']}/curriculum").json()
        assert curriculum["courses"][0]["id"] == course_id
        assert curriculum["courses"][0]["title"] == "Curso Persistido"

        course = client.get(f"/api/academy/{user['id']}/courses/{course_id}").json()
        assert course["modules"][0]["title"] == "Módulo persistido"

        glossary = client.get(f"/api/academy/{user['id']}/courses/{course_id}/glossary")
        assert glossary.status_code == 200
        assert glossary.json()["terms"][0]["term"] == "t1"

        quiz = client.get(f"/api/academy/{user['id']}/courses/{course_id}/quiz")
        assert quiz.status_code == 200
        assert quiz.json()["questions"]

        exam = client.get(f"/api/academy/{user['id']}/courses/{course_id}/exam")
        assert exam.status_code == 200
        assert exam.json()["rubric"] == "criteria"

        assignments = client.get(f"/api/academy/{user['id']}/courses/{course_id}/assignments").json()
        assert [a["type"] for a in assignments] == ["tarea", "informe", "proyecto"]

        scenario = client.get(f"/api/academy/{user['id']}/courses/{course_id}/scenario").json()
        assert scenario["scenario"] == "Un escenario práctico ya persistido para este curso."


def test_academy_glossary_quiz_exam_404_when_course_not_yet_built(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="academy-library2@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = client.get(f"/api/academy/{user['id']}/curriculum").json()["courses"][0]["id"]

        assert client.get(f"/api/academy/{user['id']}/courses/{course_id}/glossary").status_code == 404
        assert client.get(f"/api/academy/{user['id']}/courses/{course_id}/quiz").status_code == 404
        assert client.get(f"/api/academy/{user['id']}/courses/{course_id}/exam").status_code == 404
        # Legacy content types still work via on-demand fallback — unaffected by not being pre-built.
        assert client.get(f"/api/academy/{user['id']}/courses/{course_id}").status_code == 200


def test_academy_specialization_composes_base_field_courses(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    specialization = AcademicField(
        id="ai-specialization", name="Especialización en IA", category="Tecnología", icon="sparkle",
        description="Temas avanzados de inteligencia artificial.", tutor_name="Nova",
        base_field_id="computer-science",
    )
    real_get_field = academy_router.academy.get_field
    monkeypatch.setattr(
        academy_router.academy, "get_field",
        lambda fid: specialization if fid == "ai-specialization" else real_get_field(fid),
    )

    base_course_id = _seed_built_course(store, "computer-science", "BACHELOR")
    spec_course_id = _seed_built_course(store, "ai-specialization", "BACHELOR")

    with TestClient(app) as client:
        user = _onboard(client, email="academy-library3@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "ai-specialization", "level": "BACHELOR"})

        curriculum = client.get(f"/api/academy/{user['id']}/curriculum").json()
        course_ids = [c["id"] for c in curriculum["courses"]]
        # Base field's course comes first, then the specialization's own —
        # never duplicated, never regenerated under a different id.
        assert course_ids == [base_course_id, spec_course_id]
        assert [c["order"] for c in curriculum["courses"]] == [0, 1]

        # The base field's course serves its OWN content (owning field), not
        # a copy generated under the specialization.
        base_content = client.get(f"/api/academy/{user['id']}/courses/{base_course_id}").json()
        assert base_content["modules"][0]["title"] == "Módulo persistido"


def test_academy_quiz_submission_updates_competency_and_recommendation(monkeypatch, tmp_path):
    async def fake_grade_open_answer(question, rubric_note, student_answer, native_lang):
        return student_answer == "correct essay", "bien hecho" if student_answer == "correct essay" else "falta detalle"

    monkeypatch.setattr(academy_router.hf_client, "grade_open_answer", fake_grade_open_answer)
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")
    store.save_course_asset(
        "computer-science", "ASSOCIATE", "v1", course_id, "quiz",
        {
            "questions": [
                {"type": "multiple_choice", "question": "q1", "options": ["a", "b"], "correct_answer": "a"},
                {"type": "true_false", "question": "q2", "correct_answer": True},
                {"type": "open", "question": "q3", "rubric_note": "must explain X"},
            ]
        },
    )

    with TestClient(app) as client:
        user = _onboard(client, email="academy-learning1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        res = client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit",
            json={"answers": {"0": "a", "1": "True", "2": "correct essay"}},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["score"] == 1.0
        assert body["competency_score"] == 1.0
        assert all(r["correct"] for r in body["results"])

        competencies = client.get(f"/api/academy/{user['id']}/competencies").json()
        assert competencies["competencies"][0]["course_id"] == course_id
        assert competencies["competencies"][0]["title"] == "Curso Persistido"
        assert competencies["competencies"][0]["score"] == 1.0

        recommendation = client.get(f"/api/academy/{user['id']}/recommendation").json()
        # The only course is now mastered — nothing left to recommend.
        assert recommendation["all_courses_mastered"] is True
        assert recommendation["next_course_id"] is None

        achievements_res = client.get(f"/api/academy/{user['id']}/achievements").json()
        assert any(a["kind"] == "mastery" and a["course_id"] == course_id for a in achievements_res)


def test_academy_quiz_submission_missing_answers_score_zero_and_no_mastery(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")
    store.save_course_asset(
        "computer-science", "ASSOCIATE", "v1", course_id, "quiz",
        {"questions": [{"type": "multiple_choice", "question": "q1", "options": ["a", "b"], "correct_answer": "a"}]},
    )

    with TestClient(app) as client:
        user = _onboard(client, email="academy-learning2@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit", json={"answers": {}})
        assert res.status_code == 200
        assert res.json()["score"] == 0.0

        achievements_res = client.get(f"/api/academy/{user['id']}/achievements").json()
        assert not any(a["kind"] == "mastery" for a in achievements_res)


def test_academy_quiz_submit_404_when_not_built(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="academy-learning3@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        course_id = client.get(f"/api/academy/{user['id']}/curriculum").json()["courses"][0]["id"]

        res = client.post(f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit", json={"answers": {}})
        assert res.status_code == 404


def test_academy_concept_review_end_to_end(tmp_path, monkeypatch):
    from backend import db
    from backend.learning_engine import knowledge_graph

    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")
    glossary = store.load_course_asset("computer-science", "ASSOCIATE", course_id, "glossary")
    knowledge_graph.save_concepts(knowledge_graph.concepts_from_glossary("computer-science", course_id, glossary))

    with TestClient(app) as client:
        user = _onboard(client, email="academy-learning4@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        # Not due yet (a concept only becomes due after a first graded answer).
        assert client.get(f"/api/academy/{user['id']}/concepts/review").json() == []

        concept_id = knowledge_graph.concept_id(course_id, "t1")
        vocab_key = f"academic:{concept_id}"
        ans_res = client.post(
            f"/api/academy/{user['id']}/concepts/review/answer",
            json={"vocab_key": vocab_key, "correct": False},
        )
        assert ans_res.status_code == 200

        with db.cursor() as cur:
            cur.execute("UPDATE vocab_progress SET due_at='2000-01-01T00:00:00+00:00' WHERE vocab_key=?", (vocab_key,))

        due = client.get(f"/api/academy/{user['id']}/concepts/review").json()
        assert len(due) == 1
        assert due[0]["vocab_key"] == vocab_key
        assert due[0]["target_text"] == "t1"


def test_academy_analytics_reflects_time_and_competency(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")
    store.save_course_asset(
        "computer-science", "ASSOCIATE", "v1", course_id, "quiz",
        {"questions": [{"type": "multiple_choice", "question": "q1", "options": ["a", "b"], "correct_answer": "a"}]},
    )

    with TestClient(app) as client:
        user = _onboard(client, email="academy-analytics1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit", json={"answers": {"0": "a"}})
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/complete", json={"elapsed_seconds": 180})

        analytics_res = client.get(f"/api/academy/{user['id']}/analytics")
        assert analytics_res.status_code == 200
        body = analytics_res.json()
        assert body["courses_completed"] == 1
        assert body["total_time_minutes"] == 3
        assert body["competencies"][0]["course_id"] == course_id
        assert body["competencies"][0]["score"] == 1.0
        assert body["next_course_id"] is None  # only course, now mastered


def test_academy_portfolio_aggregates_real_submitted_work(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")

    with TestClient(app) as client:
        user = _onboard(client, email="academy-portfolio1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        assignments = client.get(f"/api/academy/{user['id']}/courses/{course_id}/assignments").json()
        assignment_id = assignments[0]["id"]
        client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/assignments/{assignment_id}/submit",
            json={"response": "mi respuesta"},
        )

        scenario = client.get(f"/api/academy/{user['id']}/courses/{course_id}/scenario").json()["scenario"]
        client.post(
            f"/api/academy/{user['id']}/courses/{course_id}/scenario/feedback",
            json={"scenario": scenario, "response": "mi análisis del caso"},
        )
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/complete", json={"elapsed_seconds": 90})

        portfolio_res = client.get(f"/api/academy/{user['id']}/portfolio")
        assert portfolio_res.status_code == 200
        body = portfolio_res.json()
        assert body["assignments"][0]["response"] == "mi respuesta"
        assert body["assignments"][0]["course_title"] == "Curso Persistido"
        assert body["scenarios"][0]["response"] == "mi análisis del caso"
        assert body["completed_courses"][0]["elapsed_seconds"] == 90


def test_academy_recommendation_includes_specializations_and_difficulty(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "BACHELOR")
    store.save_course_asset(
        "computer-science", "BACHELOR", "v1", course_id, "quiz",
        {"questions": [{"type": "multiple_choice", "question": "q1", "options": ["a", "b"], "correct_answer": "a"}]},
    )

    with TestClient(app) as client:
        user = _onboard(client, email="academy-reco1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "BACHELOR"})

        res = client.get(f"/api/academy/{user['id']}/recommendation")
        assert res.status_code == 200
        body = res.json()
        specialization_ids = {s["id"] for s in body["suggested_specializations"]}
        assert "artificial-intelligence" in specialization_ids
        assert body["difficulty_signal"] == "constante"  # never attempted yet

        client.post(f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit", json={"answers": {"0": "a"}})
        res2 = client.get(f"/api/academy/{user['id']}/recommendation").json()
        assert res2["all_courses_mastered"] is True
        assert res2["difficulty_signal"] is None  # nothing left to recommend a signal for


def test_academy_profile_goal_and_summary(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    _seed_built_course(store, "computer-science", "ASSOCIATE")

    with TestClient(app) as client:
        user = _onboard(client, email="academy-profile1@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})

        profile_res = client.get(f"/api/academy/{user['id']}/profile")
        assert profile_res.status_code == 200
        assert profile_res.json()["career_goal"] == ""

        goal_res = client.patch(f"/api/academy/{user['id']}/profile/goal", json={"goal": "AI Engineer"})
        assert goal_res.status_code == 200
        assert goal_res.json()["career_goal"] == "AI Engineer"

        profile_res2 = client.get(f"/api/academy/{user['id']}/profile").json()
        assert profile_res2["career_goal"] == "AI Engineer"
        assert profile_res2["interests"] == ["music"]  # from _onboard's default interests


def test_academy_profile_works_without_enrollment(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="academy-profile-noenroll@example.com")

        profile_res = client.get(f"/api/academy/{user['id']}/profile")
        assert profile_res.status_code == 200
        body = profile_res.json()
        assert body["career_goal"] == ""
        assert body["strengths_and_weaknesses"] == {"strengths": [], "weaknesses": []}
        assert body["competencies"] == {"academy": [], "language": []}
        assert body["goals"] == []


def test_academy_goals_crud_and_ownership(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="academy-goals1@example.com")
        other = _onboard(client, email="academy-goals2@example.com")
        dev_login(client, "academy-goals1@example.com")

        empty = client.get(f"/api/academy/{user['id']}/goals")
        assert empty.status_code == 200
        assert empty.json() == []

        add_res = client.post(f"/api/academy/{user['id']}/goals", json={"text": "  Pasar el B2  "})
        assert add_res.status_code == 200
        goal = add_res.json()
        assert goal["text"] == "Pasar el B2"
        assert goal["completed"] is False

        blank_res = client.post(f"/api/academy/{user['id']}/goals", json={"text": "   "})
        assert blank_res.status_code == 400

        listed = client.get(f"/api/academy/{user['id']}/goals").json()
        assert len(listed) == 1

        complete_res = client.patch(f"/api/academy/{user['id']}/goals/{goal['id']}", json={"completed": True})
        assert complete_res.status_code == 200
        assert client.get(f"/api/academy/{user['id']}/goals").json()[0]["completed"] is True

        # another user, acting on their own path, can't reach user's goal id
        dev_login(client, "academy-goals2@example.com")
        cross_res = client.patch(f"/api/academy/{other['id']}/goals/{goal['id']}", json={"completed": False})
        assert cross_res.status_code == 404
        cross_delete = client.delete(f"/api/academy/{other['id']}/goals/{goal['id']}")
        assert cross_delete.status_code == 404

        dev_login(client, "academy-goals1@example.com")
        delete_res = client.delete(f"/api/academy/{user['id']}/goals/{goal['id']}")
        assert delete_res.status_code == 200
        assert client.get(f"/api/academy/{user['id']}/goals").json() == []


def test_unified_competencies_works_without_academy_enrollment(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="unified-competencies1@example.com")

        # No academy enrollment yet — must not 404, just come back empty.
        res = client.get(f"/api/academy/{user['id']}/competencies/unified")
        assert res.status_code == 200
        assert res.json() == {"academy": [], "language": []}

        # Complete a real lesson so unit_mastery has a row to surface.
        path = client.get(f"/api/lessons/{user['id']}/path").json()
        unit_id = path[0]["id"]
        complete_res = client.post(
            f"/api/lessons/{user['id']}/complete", json={"unit_id": unit_id, "score": 0.8, "elapsed_seconds": 30}
        )
        assert complete_res.status_code == 200

        res2 = client.get(f"/api/academy/{user['id']}/competencies/unified").json()
        assert res2["academy"] == []
        assert any(c["unit_id"] == unit_id for c in res2["language"])


def test_predictions_endpoint_works_without_enrollment_and_estimates_pace_when_enrolled(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE", course_index=0)
    # _seed_built_course's own curriculum has just 1 course — replace it with
    # a 3-course one afterward so there's real "remaining courses" to see.
    store.save_curriculum(
        "computer-science", "ASSOCIATE", "v1",
        {"courses": [{"title": f"Curso {i}", "description": "Una descripción real y completa."} for i in range(3)]},
    )
    store.set_latest_version("computer-science", "ASSOCIATE", "v1")

    with TestClient(app) as client:
        user = _onboard(client, email="predictions1@example.com")

        # No enrollment yet — forgetting/dropout still real, time_to_mastery null.
        res = client.get(f"/api/academy/{user['id']}/predictions")
        assert res.status_code == 200
        body = res.json()
        assert body["forgetting_risk"]["risk_level"] == "sin_datos"
        assert body["dropout_risk"]["risk_level"] == "sin_datos"  # last_active_date starts empty
        assert body["time_to_mastery"] is None

        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/complete", json={"elapsed_seconds": 60})

        res2 = client.get(f"/api/academy/{user['id']}/predictions").json()
        assert res2["time_to_mastery"]["remaining_courses"] == 2


def test_learning_style_and_motivation_endpoints():
    with TestClient(app) as client:
        user = _onboard(client, email="style-motivation1@example.com")

        style_res = client.get(f"/api/academy/{user['id']}/learning-style")
        assert style_res.status_code == 200
        assert style_res.json()["style"] == "sin_datos"  # brand new user, no activity yet

        motivation_res = client.get(f"/api/academy/{user['id']}/motivation")
        assert motivation_res.status_code == 200
        assert motivation_res.json()["signal"] == "sin_datos"

        for score in [0.9, 0.95, 1.0]:
            client.post(
                f"/api/lessons/{user['id']}/complete",
                json={"unit_id": "practice-listen_type-A1", "score": score, "elapsed_seconds": 30},
            )

        motivation_res2 = client.get(f"/api/academy/{user['id']}/motivation").json()
        assert motivation_res2["signal"] == "buen_momentum"
        assert motivation_res2["message"] != ""


def test_mentor_endpoints_work_without_academy_enrollment(monkeypatch, tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        user = _onboard(client, email="mentor-noenroll@example.com")

        dashboard_res = client.get(f"/api/academy/{user['id']}/mentor/dashboard")
        assert dashboard_res.status_code == 200
        dashboard = dashboard_res.json()
        assert dashboard["status"]["mentor_mode"] == "neutral"
        assert dashboard["goals"] == []
        assert dashboard["mastered_concepts"] == []

        plan_res = client.get(f"/api/academy/{user['id']}/mentor/daily-plan")
        assert plan_res.status_code == 200
        assert isinstance(plan_res.json(), list)

        insights_res = client.get(f"/api/academy/{user['id']}/mentor/insights")
        assert insights_res.status_code == 200
        assert insights_res.json() == []

        kp_res = client.get(f"/api/academy/{user['id']}/mentor/knowledge-profile")
        assert kp_res.status_code == 200
        assert kp_res.json() == []


def test_mentor_dashboard_reflects_real_enrollment_data(monkeypatch, tmp_path):
    from backend.learning_engine import knowledge_graph

    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)
    course_id = _seed_built_course(store, "computer-science", "ASSOCIATE")
    # The knowledge graph is normally populated by scripts/build_academy.py
    # at build time, not per-request — simulate that step directly here.
    knowledge_graph.build_graph_for_field_level("computer-science", "ASSOCIATE", [course_id], store)

    with TestClient(app) as client:
        user = _onboard(client, email="mentor-enrolled@example.com")
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": "computer-science", "level": "ASSOCIATE"})
        client.post(f"/api/academy/{user['id']}/courses/{course_id}/quiz/submit", json={"answers": {}})

        dashboard = client.get(f"/api/academy/{user['id']}/mentor/dashboard").json()
        assert dashboard["competencies"]["academy"][0]["course_id"] == course_id
        assert isinstance(dashboard["recommendations"], list)
        assert all(r["reason"] for r in dashboard["recommendations"])

        kp = client.get(f"/api/academy/{user['id']}/mentor/knowledge-profile").json()
        assert any(c["course_id"] == course_id for c in kp)


def test_goal_milestones_generated_once_and_advance(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        import json

        return json.dumps(["Aprender Python", "Dominar Algoritmos", "Construir proyectos"])

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)

    with TestClient(app) as client:
        user = _onboard(client, email="goal-milestones1@example.com")
        goal = client.post(f"/api/academy/{user['id']}/goals", json={"text": "Convertirme en AI Engineer"}).json()

        gen_res = client.post(f"/api/academy/{user['id']}/goals/{goal['id']}/milestones")
        assert gen_res.status_code == 200
        milestones = gen_res.json()["milestones"]
        assert milestones == ["Aprender Python", "Dominar Algoritmos", "Construir proyectos"]

        advance_res = client.patch(f"/api/academy/{user['id']}/goals/{goal['id']}/milestones/advance")
        assert advance_res.status_code == 200
        assert advance_res.json()["current_milestone"] == "Dominar Algoritmos"

        # Generating again must not call the model a second time — reuses
        # the persisted milestones instead of regenerating them.
        gen_res2 = client.post(f"/api/academy/{user['id']}/goals/{goal['id']}/milestones")
        assert gen_res2.json()["milestones"] == milestones


def test_goal_milestones_404_for_unknown_goal():
    with TestClient(app) as client:
        user = _onboard(client, email="goal-milestones2@example.com")
        res = client.post(f"/api/academy/{user['id']}/goals/999999/milestones")
        assert res.status_code == 404
        res2 = client.patch(f"/api/academy/{user['id']}/goals/999999/milestones/advance")
        assert res2.status_code == 404


def test_library_search_falls_back_to_keyword_matching_without_embeddings():
    # settings.testing (see conftest.py) makes hf_client.embed_text a no-op,
    # so search_catalog's semantic_rank returns [] and it falls back to
    # plain substring matching over title/blurb — still real results.
    with TestClient(app) as client:
        user = _onboard(client, email="library-search1@example.com")
        res = client.get(f"/api/library/{user['id']}/search", params={"q": "tesoro", "limit": 5})
        assert res.status_code == 200
        results = res.json()
        assert results  # "tesoro" (treasure) matches several adventure titles
        assert all("tesoro" in b["title"].lower() for b in results)


def test_library_search_respects_level_filter():
    with TestClient(app) as client:
        user = _onboard(client, email="library-search2@example.com")
        res = client.get(f"/api/library/{user['id']}/search", params={"q": "misterio", "level": "A1", "limit": 20})
        assert res.status_code == 200
        assert all(b["level"] == "A1" for b in res.json())


def test_persona_voice_profile_endpoint():
    with TestClient(app) as client:
        _onboard(client, email="persona-voice1@example.com")
        res = client.get("/api/personas/core-elena/voice")
        assert res.status_code == 200
        profile = res.json()
        assert profile["persona_id"] == "core-elena"
        assert profile["rate"] in ("slow", "moderate", "fast")
        assert profile["pitch"] in ("low", "moderate", "high")
        assert isinstance(profile["style_tags"], list)


def test_persona_voice_profile_404_for_unknown_persona():
    with TestClient(app) as client:
        _onboard(client, email="persona-voice2@example.com")
        res = client.get("/api/personas/does-not-exist/voice")
        assert res.status_code == 404
