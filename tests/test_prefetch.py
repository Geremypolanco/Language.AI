"""Learning Runtime read-only guarantees — see routers/academy.py's and
routers/lessons.py's module docstrings for the two-phase architecture
this enforces: Phase 1 (backend/academy_library/, backend/language_
library/, both driven by scripts/build_*.py) is the only place that ever
calls the chat model to produce curriculum/course/lesson/assignment/
scenario content; Phase 2 (these routers, what a student's session
actually hits) only ever reads what Phase 1 already published.

These tests patch hf_client.chat itself (the one primitive every content-
generation call ultimately goes through) rather than a specific generate_*
method, so a regression that reintroduces a generation call through any
new code path would still be caught here."""

from fastapi.testclient import TestClient

from backend.curriculum import units_for_level
from backend.main import app
from backend.models import CEFRLevel
from backend.routers import academy as academy_router
from backend.routers import lessons as lessons_router
from conftest import dev_login


def _onboard(client, email):
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Prefetch Test", "native_lang": "Spanish", "target_lang": "Korean", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


def _explode(*args, **kwargs):
    raise AssertionError("the Learning Runtime must never call the chat model to generate content")


def test_onboarding_never_calls_the_chat_model(monkeypatch):
    from backend.hf_client import hf_client as hf_client_singleton

    async def explode_async(*args, **kwargs):
        _explode()

    monkeypatch.setattr(hf_client_singleton, "chat", explode_async)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-onboard@example.com")
        assert user["id"]


def test_enrolling_in_academy_never_calls_the_chat_model(monkeypatch):
    async def explode_async(*args, **kwargs):
        _explode()

    monkeypatch.setattr(academy_router.hf_client, "chat", explode_async)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-academy@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        res = client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
        assert res.status_code == 200

        # Nothing was built for this field — reading it back must 404,
        # never silently generate it on the spot.
        assert client.get(f"/api/academy/{user['id']}/curriculum").status_code == 404


def test_completing_a_lesson_never_calls_the_chat_model(monkeypatch):
    async def explode_async(*args, **kwargs):
        _explode()

    monkeypatch.setattr(lessons_router.hf_client, "chat", explode_async)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-complete@example.com")
        units = units_for_level(CEFRLevel.A1)

        res = client.post(
            f"/api/lessons/{user['id']}/complete",
            json={"unit_id": units[0].id, "score": 1.0, "elapsed_seconds": 60},
        )
        assert res.status_code == 200


def test_get_lesson_exercises_serves_pre_built_content_without_calling_hf_client(monkeypatch):
    from backend.academy_library.storage import FileSystemAcademyStore
    from backend.language_library.storage import language_pair_key

    monkeypatch.setattr(lessons_router.hf_client, "chat", _explode)

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-library@example.com")
        unit = units_for_level(CEFRLevel.A1)[1]
        pair_key = language_pair_key(user["target_lang"], user["native_lang"])

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileSystemAcademyStore(tmp_dir)
            store.save_course_asset(
                pair_key, unit.level.value, "v1", unit.id, "content",
                [
                    {
                        "id": "ex-0", "type": "translate_to_target", "prompt": "p", "target_text": "hola",
                        "native_text": "hello", "options": [], "correct_answer": "hola", "image_prompt": "",
                        "audio_text": "hola", "vocab_key": "greetings.hello",
                    }
                ],
            )
            store.set_latest_version(pair_key, unit.level.value, "v1")
            monkeypatch.setattr(lessons_router, "get_default_store", lambda: store)

            res = client.get(f"/api/lessons/{user['id']}/unit/{unit.id}")
            assert res.status_code == 200
            exercises = res.json()
            assert len(exercises) == 1
            assert exercises[0]["vocab_key"] == "greetings.hello"


def test_get_lesson_exercises_404_when_unit_not_built(monkeypatch):
    from backend.academy_library.storage import FileSystemAcademyStore

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-library-unbuilt@example.com")
        unit = units_for_level(CEFRLevel.A1)[1]

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileSystemAcademyStore(tmp_dir)  # empty — nothing built
            monkeypatch.setattr(lessons_router, "get_default_store", lambda: store)

            res = client.get(f"/api/lessons/{user['id']}/unit/{unit.id}")
            assert res.status_code == 404
