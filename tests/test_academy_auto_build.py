import asyncio
import json

from backend import academy
from backend.academy_library import auto_build, build
from backend.academy_library.storage import FileSystemAcademyStore
from backend.models import AcademicLevel

_VALID_CURRICULUM_JSON = json.dumps([{"title": "Course A", "description": "a real, complete description of course A"}])
_VALID_MODULES_JSON = json.dumps([{"title": "M1", "content": "x" * 100}, {"title": "M2", "content": "y" * 100}])
_VALID_GLOSSARY_JSON = json.dumps({"terms": [{"term": f"t{i}", "definition": f"def{i}"} for i in range(5)]})
_VALID_QUIZ_JSON = json.dumps(
    {"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "note"} for i in range(4)]}
)
_VALID_EXAM_JSON = json.dumps(
    {"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "note"} for i in range(8)], "rubric": "criteria"}
)
_VALID_ASSIGNMENTS_JSON = json.dumps(
    [
        {"type": "tarea", "title": "T", "instructions": "do this thing please"},
        {"type": "informe", "title": "I", "instructions": "write this report please"},
        {"type": "proyecto", "title": "P", "instructions": "build this project please"},
    ]
)
_VALID_SCENARIO_TEXT = "a" * 50
_VALID_METADATA_JSON = json.dumps(
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
_VALID_BIOGRAPHY_JSON = json.dumps(
    {
        "career_highlights": ["18 años como CTO de una empresa de logística global", "Fundó dos startups de software"],
        "philosophy": "La precisión y la relevancia en el mundo real por encima de todo.",
        "correction_focus": "afirmaciones vagas o sin sustento",
        "system_voice": "You are a rigorous, real-world-grounded professor who corrects imprecision immediately.",
        "motivational_style": "Enmarca cada corrección en términos de lo que desbloquea profesionalmente.",
    }
)

_ONE_COURSE_ASSET_RESPONSES = [
    _VALID_MODULES_JSON, _VALID_GLOSSARY_JSON, _VALID_QUIZ_JSON, _VALID_EXAM_JSON,
    _VALID_ASSIGNMENTS_JSON, _VALID_SCENARIO_TEXT, _VALID_METADATA_JSON,
]
_FAST_PATH_RESPONSES = [_VALID_CURRICULUM_JSON, *_ONE_COURSE_ASSET_RESPONSES, _VALID_BIOGRAPHY_JSON]


def _queue_responses(monkeypatch, responses: list[str]):
    from backend import hf_client as hf_client_module

    calls = iter(responses)

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(calls)

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)


def _explode_on_chat(monkeypatch):
    from backend import hf_client as hf_client_module

    async def explode(*args, **kwargs):
        raise AssertionError("hf_client.chat must not be called for already-complete content")

    monkeypatch.setattr(hf_client_module.hf_client, "chat", explode)


def _seed_full_course(store, field_id, level, course_index=0, title="Existing"):
    course_id = f"{field_id}:{level}:{course_index}"
    store.save_course_asset(field_id, level, "v1", course_id, "content", {"modules": [{"title": "m", "content": "z" * 100}]})
    store.save_course_asset(field_id, level, "v1", course_id, "glossary", {"terms": [{"term": "t", "definition": "d"}] * 5})
    store.save_course_asset(
        field_id, level, "v1", course_id, "quiz",
        {"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "n"} for i in range(4)]},
    )
    store.save_course_asset(
        field_id, level, "v1", course_id, "exam",
        {"questions": [{"type": "open", "question": f"q{i}?", "rubric_note": "n"} for i in range(8)], "rubric": "criteria"},
    )
    store.save_course_asset(field_id, level, "v1", course_id, "assignments", json.loads(_VALID_ASSIGNMENTS_JSON))
    store.save_course_asset(field_id, level, "v1", course_id, "scenario", _VALID_SCENARIO_TEXT)
    store.save_course_asset(field_id, level, "v1", course_id, "metadata", json.loads(_VALID_METADATA_JSON))
    return course_id


# ── ensure_field_level_started ──────────────────────────────────────────


def test_ensure_field_level_started_builds_and_flips_on_first_call(tmp_path, monkeypatch):
    # A real BACHELOR field needs 24 courses' worth of curriculum to pass
    # validation (min_courses = course_count // 2) — pin it to 1 so the
    # single-course fixture curriculum below is enough, same trick
    # test_academy_library.py's build_field_level tests already use.
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    _queue_responses(monkeypatch, _FAST_PATH_RESPONSES)
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")

    version = asyncio.run(auto_build.ensure_field_level_started(store, field, AcademicLevel.BACHELOR, "es"))
    assert version is not None
    assert store.get_latest_version("computer-science", "BACHELOR") == version
    course_id = "computer-science:BACHELOR:0"
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "content") is not None
    assert store.load_field_biography("computer-science") is not None


def test_ensure_field_level_started_is_a_no_op_when_already_started(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    store.save_curriculum(
        "computer-science", "BACHELOR", "v1",
        {"courses": [{"title": "Existing", "description": "already here, real description"}]},
    )
    store.set_latest_version("computer-science", "BACHELOR", "v1")

    _explode_on_chat(monkeypatch)  # zero AI calls expected
    version = asyncio.run(auto_build.ensure_field_level_started(store, field, AcademicLevel.BACHELOR, "es"))
    assert version == "v1"


def test_ensure_field_level_started_returns_none_when_generation_fails(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "not json at all"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")

    version = asyncio.run(auto_build.ensure_field_level_started(store, field, AcademicLevel.BACHELOR, "es"))
    assert version is None
    assert store.get_latest_version("computer-science", "BACHELOR") is None


# ── ensure_course_built ──────────────────────────────────────────────────


def test_ensure_course_built_only_requests_missing_kinds(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    course_id = "computer-science:BACHELOR:0"
    store.save_curriculum(
        "computer-science", "BACHELOR", "v1",
        {"courses": [{"title": "Course A", "description": "a real, complete description of course A"}]},
    )
    store.set_latest_version("computer-science", "BACHELOR", "v1")
    store.save_course_asset(
        "computer-science", "BACHELOR", "v1", course_id, "content", {"modules": [{"title": "already-built", "content": "z" * 100}]}
    )

    _queue_responses(monkeypatch, _ONE_COURSE_ASSET_RESPONSES[1:])  # everything except content (already built)
    failures = asyncio.run(
        auto_build.ensure_course_built(store, field, AcademicLevel.BACHELOR, course_id, "Course A", "desc", "es")
    )
    assert failures == []
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "content")["modules"][0]["title"] == "already-built"
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "glossary") is not None
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "metadata") is not None


def test_ensure_course_built_returns_early_when_no_curriculum_persisted(tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    failures = asyncio.run(
        auto_build.ensure_course_built(store, field, AcademicLevel.BACHELOR, "computer-science:BACHELOR:0", "T", "d", "es")
    )
    assert failures and failures[0][0] == "curriculum"


# ── ensure_background_completion ─────────────────────────────────────────


def test_ensure_background_completion_skips_when_already_complete(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    store.save_curriculum(
        "computer-science", "BACHELOR", "v1",
        {"courses": [{"title": "Course A", "description": "a real, complete description of course A"}]},
    )
    store.set_latest_version("computer-science", "BACHELOR", "v1")
    _seed_full_course(store, "computer-science", "BACHELOR")

    _explode_on_chat(monkeypatch)  # zero AI calls expected — nothing left to build

    async def _run():
        auto_build.ensure_background_completion(store, field, AcademicLevel.BACHELOR, "es")
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        await asyncio.gather(*pending)

    asyncio.run(_run())


def test_ensure_background_completion_finishes_remaining_courses(tmp_path, monkeypatch):
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    store.save_curriculum(
        "computer-science", "BACHELOR", "v1",
        {
            "courses": [
                {"title": "Course A", "description": "a real, complete description of course A"},
                {"title": "Course B", "description": "a real, complete description of course B"},
            ]
        },
    )
    store.set_latest_version("computer-science", "BACHELOR", "v1")
    _seed_full_course(store, "computer-science", "BACHELOR", course_index=0)

    # Course 1 needs all 7 kinds, then one biography call.
    _queue_responses(monkeypatch, [*_ONE_COURSE_ASSET_RESPONSES, _VALID_BIOGRAPHY_JSON])

    async def _run():
        auto_build.ensure_background_completion(store, field, AcademicLevel.BACHELOR, "es")
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        await asyncio.gather(*pending)

    asyncio.run(_run())

    assert store.load_course_asset("computer-science", "BACHELOR", "computer-science:BACHELOR:1", "content") is not None
    assert store.load_field_biography("computer-science") is not None
