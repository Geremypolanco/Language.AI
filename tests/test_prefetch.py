"""Background prefetch tests — see users.py's _prefetch_units, lessons.py's
_prefetch_unit/_next_unit_after, and academy.py's _prefetch_first_course.
The goal all three serve: a learner's next click should hit an already-
warm disk cache instead of waiting on an AI generation, without ever
generating content for units/courses nobody has committed to yet.

FastAPI's TestClient runs BackgroundTasks synchronously as part of the
request/response cycle (they execute after the handler returns, before the
test gets its response back), so these tests can assert on prefetch side
effects immediately after the triggering request completes — no polling
or real backgrounding needed."""

from fastapi.testclient import TestClient

from backend.curriculum import ALPHABET_TOPIC, units_for_level
from backend.main import app
from backend.models import CEFRLevel
from backend.routers import lessons as lessons_router
from backend.routers import users as users_router
from conftest import dev_login


def _onboard(client, email):
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Prefetch Test", "native_lang": "Spanish", "target_lang": "Korean", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


def test_next_unit_after_returns_the_following_unit_in_the_skill_tree():
    units = units_for_level(CEFRLevel.A1)
    assert lessons_router._next_unit_after(units[0].id).id == units[1].id


def test_next_unit_after_returns_none_for_the_last_unit_and_unknown_ids():
    from backend.curriculum import all_units

    assert lessons_router._next_unit_after(all_units()[-1].id) is None
    assert lessons_router._next_unit_after("practice-listen_type-A1") is None
    assert lessons_router._next_unit_after("does-not-exist") is None


def test_onboarding_prefetches_the_first_units_exercises(monkeypatch):
    # users.py's _prefetch_units imports hf_client locally (deferred import
    # inside the function body, not a module-level name on users_router) —
    # patch the shared singleton instance directly instead, which every
    # importer sees regardless of how they imported it.
    from backend.hf_client import hf_client as hf_client_singleton

    seen_units = []
    original = hf_client_singleton.generate_exercises

    async def spy(req, mix_override=None):
        seen_units.append(req.unit.id)
        return await original(req, mix_override)

    monkeypatch.setattr(hf_client_singleton, "generate_exercises", spy)

    with TestClient(app) as client:
        _onboard(client, email="prefetch-onboard@example.com")

    expected = [u.id for u in units_for_level(CEFRLevel.A1)[: users_router._PREFETCH_UNIT_COUNT]]
    assert seen_units == expected
    # The alphabet unit is unit 0 for A1 — prefetch must still warm it like
    # any other unit; only free-practice mode skips it as a content seed.
    assert units_for_level(CEFRLevel.A1)[0].topic == ALPHABET_TOPIC


def test_completing_a_lesson_prefetches_only_the_next_unit(monkeypatch):
    seen_units = []
    original = lessons_router.hf_client.generate_exercises

    async def spy(req, mix_override=None):
        seen_units.append(req.unit.id)
        return await original(req, mix_override)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-complete@example.com")
        units = units_for_level(CEFRLevel.A1)

        monkeypatch.setattr(lessons_router.hf_client, "generate_exercises", spy)
        res = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": units[0].id, "score": 1.0, "elapsed_seconds": 60},
        )
        assert res.status_code == 200

    assert seen_units == [units[1].id]


def test_completing_the_last_unit_does_not_prefetch_anything(monkeypatch):
    from backend.curriculum import all_units

    seen_units = []
    original = lessons_router.hf_client.generate_exercises

    async def spy(req, mix_override=None):
        seen_units.append(req.unit.id)
        return await original(req, mix_override)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-last@example.com")
        last_unit_id = all_units()[-1].id

        monkeypatch.setattr(lessons_router.hf_client, "generate_exercises", spy)
        res = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": last_unit_id, "score": 1.0, "elapsed_seconds": 60},
        )
        assert res.status_code == 200

    assert seen_units == []


def test_enrolling_in_academy_prefetches_curriculum_and_first_course(monkeypatch):
    from backend.routers import academy as academy_router

    curriculum_calls = []
    course_calls = []
    assignment_calls = []

    original_curriculum = academy_router.hf_client.generate_curriculum
    original_course = academy_router.hf_client.generate_course_content
    original_assignments = academy_router.hf_client.generate_assignments

    async def curriculum_spy(field, level, native_lang):
        curriculum_calls.append((field.id, level))
        return await original_curriculum(field, level, native_lang)

    async def course_spy(field, level, course_id, title, description, native_lang):
        course_calls.append(course_id)
        return await original_course(field, level, course_id, title, description, native_lang)

    async def assignments_spy(field, level, course_id, title, description, native_lang):
        assignment_calls.append(course_id)
        return await original_assignments(field, level, course_id, title, description, native_lang)

    monkeypatch.setattr(academy_router.hf_client, "generate_curriculum", curriculum_spy)
    monkeypatch.setattr(academy_router.hf_client, "generate_course_content", course_spy)
    monkeypatch.setattr(academy_router.hf_client, "generate_assignments", assignments_spy)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-academy@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        res = client.post(
            f"/api/academy/{user['id']}/enroll",
            json={"field_id": field_id, "level": "ASSOCIATE"},
        )
        assert res.status_code == 200

    assert len(curriculum_calls) == 1
    assert curriculum_calls[0][0] == field_id
    assert len(course_calls) == 1
    assert len(assignment_calls) == 1
    assert course_calls == assignment_calls  # same first course both times
