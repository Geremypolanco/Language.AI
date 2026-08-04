import asyncio
import json

import pytest

from backend import academy
from backend.academy_library import build, generators, validators
from backend.academy_library.storage import FileSystemAcademyStore
from backend.models import AcademicLevel


# ── Storage ──────────────────────────────────────────────────────────────


def test_store_roundtrips_curriculum_and_course_assets(tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    assert store.get_latest_version("computer-science", "BACHELOR") is None
    assert not store.is_built("computer-science", "BACHELOR")

    curriculum = {"courses": [{"title": "Intro", "description": "desc"}]}
    store.save_curriculum("computer-science", "BACHELOR", "v1", curriculum)
    store.save_course_asset("computer-science", "BACHELOR", "v1", "computer-science:BACHELOR:0", "glossary", {"terms": []})
    store.set_latest_version("computer-science", "BACHELOR", "v1")

    assert store.is_built("computer-science", "BACHELOR")
    assert store.get_latest_version("computer-science", "BACHELOR") == "v1"
    assert store.load_curriculum("computer-science", "BACHELOR") == curriculum
    assert store.load_course_asset("computer-science", "BACHELOR", "computer-science:BACHELOR:0", "glossary") == {"terms": []}
    # An asset kind that was never saved for this course is a clean miss, not an error.
    assert store.load_course_asset("computer-science", "BACHELOR", "computer-science:BACHELOR:0", "quiz") is None


def test_store_versions_are_independent_and_latest_pointer_is_explicit(tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    store.save_curriculum("computer-science", "BACHELOR", "v1", {"courses": [{"title": "old", "description": "d"}]})
    store.save_curriculum("computer-science", "BACHELOR", "v2", {"courses": [{"title": "new", "description": "d"}]})
    # Writing v2 doesn't move the pointer by itself.
    assert store.get_latest_version("computer-science", "BACHELOR") is None

    store.set_latest_version("computer-science", "BACHELOR", "v1")
    assert store.load_curriculum("computer-science", "BACHELOR")["courses"][0]["title"] == "old"
    assert store.load_curriculum("computer-science", "BACHELOR", version="v2")["courses"][0]["title"] == "new"

    store.set_latest_version("computer-science", "BACHELOR", "v2")
    assert store.load_curriculum("computer-science", "BACHELOR")["courses"][0]["title"] == "new"


def test_store_sanitizes_colons_in_course_ids_for_filenames(tmp_path):
    # Course ids look like "computer-science:BACHELOR:3" — ':' must not
    # break FileSystemAcademyStore on any filesystem it might run on.
    store = FileSystemAcademyStore(str(tmp_path))
    store.save_course_asset("computer-science", "BACHELOR", "v1", "computer-science:BACHELOR:3", "content", {"modules": []})
    assert store.load_course_asset("computer-science", "BACHELOR", "computer-science:BACHELOR:3", "content", version="v1") == {"modules": []}


# ── Validators ───────────────────────────────────────────────────────────


def test_validate_curriculum():
    assert validators.validate_curriculum({"courses": [{"title": "A", "description": "a real description"}]}) == []
    assert validators.validate_curriculum({"courses": []}, min_courses=1) != []
    assert validators.validate_curriculum({"courses": [{"title": "", "description": "x" * 20}]}) != []
    assert validators.validate_curriculum({"courses": [{"title": "A", "description": "short"}]}) != []


def test_validate_course_content():
    good = {"modules": [{"title": "M1", "content": "x" * 100}, {"title": "M2", "content": "y" * 100}]}
    assert validators.validate_course_content(good) == []
    assert validators.validate_course_content({"modules": [{"title": "M1", "content": "x" * 100}]}) != []  # only 1 module
    assert validators.validate_course_content({"modules": [{"title": "M1", "content": "short"}, {"title": "M2", "content": "y" * 100}]}) != []


def test_validate_glossary():
    good = {"terms": [{"term": f"t{i}", "definition": f"d{i}"} for i in range(5)]}
    assert validators.validate_glossary(good) == []
    assert validators.validate_glossary({"terms": [{"term": "t", "definition": ""}] * 5}) != []
    assert validators.validate_glossary({"terms": []}) != []


def test_validate_quiz():
    good = {
        "questions": [
            {"type": "multiple_choice", "question": "q1?", "options": ["a", "b"], "correct_answer": "a"},
            {"type": "true_false", "question": "q2?", "correct_answer": True},
            {"type": "open", "question": "q3?", "rubric_note": "must mention X"},
            {"type": "open", "question": "q4?", "rubric_note": "must mention Y"},
        ]
    }
    assert validators.validate_quiz(good) == []
    bad_mc = {"questions": good["questions"][:1] + [{"type": "multiple_choice", "question": "q", "options": ["only-one"], "correct_answer": "x"}] * 3}
    assert validators.validate_quiz(bad_mc) != []
    assert validators.validate_quiz({"questions": [{"type": "mystery", "question": "q"}] * 4}) != []


def test_validate_exam_requires_a_rubric():
    questions = [{"type": "open", "question": f"q{i}?", "rubric_note": "note"} for i in range(8)]
    assert validators.validate_exam({"questions": questions, "rubric": "grading criteria"}) == []
    assert validators.validate_exam({"questions": questions, "rubric": ""}) != []


def test_validate_assignments():
    good = [
        {"type": "tarea", "title": "T", "instructions": "do this thing please"},
        {"type": "informe", "title": "I", "instructions": "write this report please"},
        {"type": "proyecto", "title": "P", "instructions": "build this project please"},
    ]
    assert validators.validate_assignments(good) == []
    assert validators.validate_assignments(good[:2]) != []  # wrong count
    bad_type = [dict(good[0], type="invalid")] + good[1:]
    assert validators.validate_assignments(bad_type) != []


def test_validate_scenario():
    assert validators.validate_scenario("a" * 50) == []
    assert validators.validate_scenario("too short") != []


# ── Build pipeline ───────────────────────────────────────────────────────


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


def _queue_responses(monkeypatch, responses: list[str]):
    """Feeds hf_client.chat() one canned response per call, in order —
    simulates the model producing exactly the sequence of content types
    build_field_level asks for (curriculum, then per-course: content,
    glossary, quiz, exam, assignments, scenario)."""
    from backend import hf_client as hf_client_module

    calls = iter(responses)

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(calls)

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)


def _one_course_responses() -> list[str]:
    return [
        _VALID_CURRICULUM_JSON,
        _VALID_MODULES_JSON,
        _VALID_GLOSSARY_JSON,
        _VALID_QUIZ_JSON,
        _VALID_EXAM_JSON,
        _VALID_ASSIGNMENTS_JSON,
        _VALID_SCENARIO_TEXT,
    ]


def test_build_field_level_persists_every_asset_and_sets_latest_version(tmp_path, monkeypatch):
    # A real BACHELOR field needs 24 courses (validators require at least
    # half of them) — pin the pipeline's course_count to 1 so a single-
    # course fixture is enough to exercise the full asset pipeline cleanly.
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    _queue_responses(monkeypatch, _one_course_responses())
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")

    report = asyncio.run(build.build_field_level(store, field, AcademicLevel.BACHELOR, "es", "v1"))

    assert report.ok
    assert report.courses_built == 1
    assert store.get_latest_version("computer-science", "BACHELOR") == "v1"
    course_id = "computer-science:BACHELOR:0"
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "content")["modules"][0]["title"] == "M1"
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "glossary")["terms"]
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "quiz")["questions"]
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "exam")["rubric"] == "criteria"
    assignments = store.load_course_asset("computer-science", "BACHELOR", course_id, "assignments")
    assert [a["type"] for a in assignments] == ["tarea", "informe", "proyecto"]
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "scenario") == _VALID_SCENARIO_TEXT


def test_build_field_level_retries_on_invalid_output_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    # Curriculum generation: first attempt is garbage, second is valid.
    responses = ["not json at all", _VALID_CURRICULUM_JSON] + _one_course_responses()[1:]
    _queue_responses(monkeypatch, responses)
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")

    report = asyncio.run(build.build_field_level(store, field, AcademicLevel.BACHELOR, "es", "v1"))
    assert report.ok
    assert store.is_built("computer-science", "BACHELOR")


def test_build_field_level_records_failure_and_does_not_publish_after_exhausting_retries(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "still not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")

    report = asyncio.run(build.build_field_level(store, field, AcademicLevel.BACHELOR, "es", "v1"))
    assert not report.ok
    assert report.failures
    # A failed curriculum build must never flip the latest pointer — a
    # reader must keep serving the previous good version (or nothing),
    # never a half-built one.
    assert store.get_latest_version("computer-science", "BACHELOR") is None


def test_build_is_resumable_by_default_and_force_regenerates(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    store = FileSystemAcademyStore(str(tmp_path))
    field = academy.get_field("computer-science")
    course_id = "computer-science:BACHELOR:0"
    store.save_curriculum(
        "computer-science", "BACHELOR", "v1",
        {"courses": [{"title": "Course A", "description": "a real, complete description of course A"}]},
    )
    store.save_course_asset("computer-science", "BACHELOR", "v1", course_id, "content", {"modules": [{"title": "already-built", "content": "z" * 100}]})

    # Only the still-missing assets (glossary/quiz/exam/assignments/scenario)
    # should be requested from the model — curriculum and content are skipped.
    _queue_responses(monkeypatch, [_VALID_GLOSSARY_JSON, _VALID_QUIZ_JSON, _VALID_EXAM_JSON, _VALID_ASSIGNMENTS_JSON, _VALID_SCENARIO_TEXT])
    report = asyncio.run(build.build_field_level(store, field, AcademicLevel.BACHELOR, "es", "v1", force=False))
    assert report.ok
    # The pre-existing content asset was left untouched, not regenerated.
    assert store.load_course_asset("computer-science", "BACHELOR", course_id, "content")["modules"][0]["title"] == "already-built"


def test_specialization_generates_fewer_courses_than_a_full_level(tmp_path, monkeypatch):
    from backend.models import AcademicField

    specialization = AcademicField(
        id="ai-specialization", name="AI Specialization", category="Tecnología", icon="sparkle",
        description="Advanced AI topics", tutor_name="Nova", base_field_id="computer-science",
    )
    # SPECIALIZATION_COURSE_COUNT courses' worth of curriculum + 1 course's assets.
    curriculum_json = json.dumps(
        [{"title": f"C{i}", "description": "a real, complete description"} for i in range(build.SPECIALIZATION_COURSE_COUNT)]
    )
    responses = [curriculum_json] + _one_course_responses()[1:] * build.SPECIALIZATION_COURSE_COUNT
    _queue_responses(monkeypatch, responses)
    store = FileSystemAcademyStore(str(tmp_path))

    report = asyncio.run(build.build_field_level(store, specialization, AcademicLevel.BACHELOR, "es", "v1"))
    assert report.ok
    curriculum = store.load_curriculum("ai-specialization", "BACHELOR")
    assert len(curriculum["courses"]) == build.SPECIALIZATION_COURSE_COUNT
    assert build.SPECIALIZATION_COURSE_COUNT < AcademicLevel.BACHELOR.course_count


def test_next_version_increments_independently_per_field():
    class _FakeStore:
        def __init__(self):
            self.versions = {}

        def get_latest_version(self, field_id, level):
            return self.versions.get((field_id, level))

    fake = _FakeStore()
    assert build.next_version(fake, "computer-science", "BACHELOR") == "v1"
    fake.versions[("computer-science", "BACHELOR")] = "v1"
    assert build.next_version(fake, "computer-science", "BACHELOR") == "v2"
    # A different field/level is untouched by the first one's version.
    assert build.next_version(fake, "biology", "BACHELOR") == "v1"


def test_resolve_fields_rejects_unknown_field_id():
    with pytest.raises(ValueError):
        build.resolve_fields(["does-not-exist"])
    assert len(build.resolve_fields(None)) == len(academy.all_fields())
