import asyncio
import json

from backend import academy
from backend.academy_library import build, proactive_builder
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

_ONE_FIELD_LEVEL_RESPONSES = [
    _VALID_CURRICULUM_JSON, _VALID_MODULES_JSON, _VALID_GLOSSARY_JSON, _VALID_QUIZ_JSON,
    _VALID_EXAM_JSON, _VALID_ASSIGNMENTS_JSON, _VALID_SCENARIO_TEXT, _VALID_METADATA_JSON,
    _VALID_BIOGRAPHY_JSON,
]


def _queue_responses(monkeypatch, responses: list[str]):
    from backend import hf_client as hf_client_module

    calls = iter(responses)

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(calls)

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)


def _one_field_catalog(monkeypatch):
    field = academy.get_field("computer-science")
    monkeypatch.setattr(proactive_builder.academy, "all_fields", lambda: [field])
    return field


def test_next_incomplete_unit_is_none_for_an_empty_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive_builder.academy, "all_fields", lambda: [])
    store = FileSystemAcademyStore(str(tmp_path))
    assert asyncio.run(proactive_builder._next_incomplete_unit(store)) is None


def test_build_one_step_completes_the_whole_catalog_then_stops(tmp_path, monkeypatch):
    field = _one_field_catalog(monkeypatch)
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    # One field's fast path (curriculum + 1-course build + biography) fully
    # completes a (field, level) pair in a single _build_one_step call —
    # queue that many responses per AcademicLevel this fake catalog has.
    _queue_responses(monkeypatch, _ONE_FIELD_LEVEL_RESPONSES * len(list(AcademicLevel)))
    store = FileSystemAcademyStore(str(tmp_path))

    steps = 0
    while asyncio.run(proactive_builder._build_one_step(store, "es")):
        steps += 1
        assert steps <= len(list(AcademicLevel)), "did not converge — would loop forever"

    assert steps == len(list(AcademicLevel))
    for level in AcademicLevel:
        assert store.is_built(field.id, level.value)
        assert store.load_field_biography(field.id) is not None


def test_build_one_step_is_idempotent_once_the_catalog_is_complete(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    field = _one_field_catalog(monkeypatch)
    monkeypatch.setattr(build, "_course_count_for", lambda field, level: 1)
    _queue_responses(monkeypatch, _ONE_FIELD_LEVEL_RESPONSES * len(list(AcademicLevel)))
    store = FileSystemAcademyStore(str(tmp_path))

    while asyncio.run(proactive_builder._build_one_step(store, "es")):
        pass

    async def explode(*args, **kwargs):
        raise AssertionError("hf_client.chat must not be called once the catalog is fully built")

    monkeypatch.setattr(hf_client_module.hf_client, "chat", explode)
    assert asyncio.run(proactive_builder._build_one_step(store, "es")) is False


def test_run_periodic_academy_build_cancels_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(proactive_builder.academy, "all_fields", lambda: [])
    monkeypatch.setattr(proactive_builder, "get_default_store", lambda: FileSystemAcademyStore(str(tmp_path)))

    async def _run():
        task = asyncio.create_task(proactive_builder.run_periodic_academy_build(interval_s=0.01))
        await asyncio.sleep(0.03)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
