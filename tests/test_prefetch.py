"""Background prefetch tests — see users.py's _prefetch_units, lessons.py's
_prefetch_unit/_next_unit_after, and routers/academy.py's enroll() (which
now runs the academy_library build pipeline directly — see
academy_library/auto_build.py — rather than a separate prefetch helper).
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


def test_get_lesson_exercises_serves_pre_built_content_without_calling_hf_client(monkeypatch):
    from backend.academy_library.storage import FileSystemAcademyStore
    from backend.language_library.storage import language_pair_key

    async def explode(*args, **kwargs):
        raise AssertionError("hf_client.generate_exercises must not run for a pre-built unit")

    monkeypatch.setattr(lessons_router.hf_client, "generate_exercises", explode)

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


def test_get_lesson_exercises_falls_back_when_unit_not_built(monkeypatch):
    from backend.academy_library.storage import FileSystemAcademyStore

    with TestClient(app) as client:
        user = _onboard(client, email="prefetch-library-fallback@example.com")
        unit = units_for_level(CEFRLevel.A1)[1]

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileSystemAcademyStore(tmp_dir)  # empty — nothing built
            monkeypatch.setattr(lessons_router, "get_default_store", lambda: store)

            res = client.get(f"/api/lessons/{user['id']}/unit/{unit.id}")
            assert res.status_code == 200
            assert len(res.json()) > 0  # existing on-demand path still works


def test_enrolling_in_academy_builds_and_persists_curriculum_and_first_course(monkeypatch, tmp_path):
    """Enrollment now runs the same resumable academy_library build
    pipeline the proactive builder uses (see academy_library/auto_build.py's
    ensure_field_level_started) instead of the old _prefetch_first_course
    background task, which called hf_client.generate_* directly and never
    persisted anything. This verifies the new mechanism actually builds
    and PERSISTS the curriculum + first course (every asset kind, plus a
    tutor biography), not just warms an ephemeral, unpersisted cache."""
    import json

    from backend import hf_client as hf_client_module
    from backend.academy_library import build as build_module
    from backend.academy_library.storage import FileSystemAcademyStore
    from backend.routers import academy as academy_router

    valid_curriculum = json.dumps([{"title": "Course A", "description": "a real, complete description of course A"}])
    valid_modules = json.dumps([{"title": "M1", "content": "x" * 100}, {"title": "M2", "content": "y" * 100}])
    valid_glossary = json.dumps({"terms": [{"term": f"t{i}", "definition": f"def{i}"} for i in range(5)]})
    valid_quiz = json.dumps({"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "n"} for i in range(4)]})
    valid_exam = json.dumps(
        {"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "n"} for i in range(8)], "rubric": "criteria"}
    )
    valid_assignments = json.dumps(
        [
            {"type": "tarea", "title": "T", "instructions": "do this thing please"},
            {"type": "informe", "title": "I", "instructions": "write this report please"},
            {"type": "proyecto", "title": "P", "instructions": "build this project please"},
        ]
    )
    valid_scenario = "a" * 50
    valid_metadata = json.dumps(
        {
            "learning_objectives": ["Objective 1", "Objective 2"],
            "prerequisite_concepts": ["Concept A"],
            "bloom_level": "apply",
            "estimated_hours": 10,
            "difficulty": "intermediate",
            "cognitive_load": "medium",
            "required_vocabulary": ["term1"],
            "expected_competencies": ["competency1"],
            "practical_outcomes": ["outcome1"],
            "assessment_strategy": "A short quiz and a hands-on project.",
        }
    )
    valid_biography = json.dumps(
        {
            "career_highlights": ["18 years as CTO of a logistics company", "Founded two startups"],
            "philosophy": "Precision and real-world relevance above all else.",
            "correction_focus": "vague or unsupported claims",
            "system_voice": "You are a rigorous, real-world-grounded professor.",
            "motivational_style": "Frame every correction in terms of what it unlocks professionally.",
        }
    )
    responses = iter(
        [valid_curriculum, valid_modules, valid_glossary, valid_quiz, valid_exam, valid_assignments, valid_scenario, valid_metadata, valid_biography]
    )

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(responses)

    # A real ASSOCIATE field needs 12 courses' worth of curriculum to pass
    # validation (min_courses = course_count // 2) — pin it to 1 so the
    # single-course fixture above is enough (same trick test_academy_
    # library.py's build tests use).
    monkeypatch.setattr(build_module, "_course_count_for", lambda field, level: 1)

    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(academy_router, "get_default_store", lambda: store)

    with TestClient(app) as client:
        # Onboarding triggers its own (unrelated) language-lesson prefetch,
        # which also calls hf_client.chat — install the curated academy
        # response queue only after that's done, so it doesn't steal from it.
        user = _onboard(client, email="prefetch-academy@example.com")
        monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        res = client.post(
            f"/api/academy/{user['id']}/enroll",
            json={"field_id": field_id, "level": "ASSOCIATE"},
        )
        assert res.status_code == 200

    assert store.get_latest_version(field_id, "ASSOCIATE") is not None
    course_id = f"{field_id}:ASSOCIATE:0"
    assert store.load_course_asset(field_id, "ASSOCIATE", course_id, "content") is not None
    assert store.load_course_asset(field_id, "ASSOCIATE", course_id, "assignments") is not None
    assert store.load_field_biography(field_id) is not None
