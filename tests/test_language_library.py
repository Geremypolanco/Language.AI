import asyncio
import json

from backend.curriculum import units_for_level
from backend.language_library import build, generators, validators
from backend.language_library.storage import FileSystemAcademyStore, language_pair_key
from backend.models import CEFRLevel, Exercise, ExerciseType


# ── Storage ──────────────────────────────────────────────────────────────


def test_language_pair_key_format():
    assert language_pair_key("Korean", "Spanish") == "Korean:Spanish"


def test_store_supports_flashcards_kind(tmp_path):
    store = FileSystemAcademyStore(str(tmp_path))
    store.save_course_asset("en:es", "A1", "v1", "A1-0", "flashcards", [{"vocab_key": "greetings.hello"}])
    assert store.load_course_asset("en:es", "A1", "A1-0", "flashcards", version="v1") == [{"vocab_key": "greetings.hello"}]


# ── Validators ───────────────────────────────────────────────────────────


def _make_exercise(**overrides) -> Exercise:
    defaults = dict(
        id="ex-0-hello", type=ExerciseType.TRANSLATE_TO_TARGET, prompt="Traduce", target_text="hello",
        native_text="hola", options=[], correct_answer="hello", image_prompt="", audio_text="hello",
        vocab_key="greetings.hello",
    )
    defaults.update(overrides)
    return Exercise(**defaults)


def test_validate_exercise_list_valid():
    assert validators.validate_exercise_list([_make_exercise()]) == []


def test_validate_exercise_list_rejects_empty():
    assert validators.validate_exercise_list([]) != []


def test_validate_exercise_list_rejects_missing_vocab_key():
    ex = _make_exercise(vocab_key="")
    assert any("vocab_key" in p for p in validators.validate_exercise_list([ex]))


def test_validate_exercise_list_rejects_choice_type_without_options():
    ex = _make_exercise(type=ExerciseType.MULTIPLE_CHOICE, options=[])
    assert any("options" in p for p in validators.validate_exercise_list([ex]))


def test_validate_flashcards():
    assert validators.validate_flashcards([{"vocab_key": "k", "target_text": "t"}]) == []
    assert validators.validate_flashcards([{"vocab_key": "k"}]) != []
    assert validators.validate_flashcards([{"target_text": "t"}]) != []


# ── Generators ───────────────────────────────────────────────────────────


_VALID_EXERCISE_JSON = json.dumps(
    [
        {
            "type": "translate_to_target", "prompt": "Traduce", "target_text": "hello", "native_text": "hola",
            "options": [], "correct_answer": "hello", "image_prompt": "", "audio_text": "hello",
            "vocab_key": "greetings.hello",
        }
    ]
)


def test_generate_unit_exercises_success(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return _VALID_EXERCISE_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    unit = units_for_level(CEFRLevel.A1)[1]  # a normal, non-alphabet unit
    exercises = asyncio.run(generators.generate_unit_exercises(unit, "English", "Spanish"))
    assert len(exercises) == 1
    assert exercises[0].vocab_key == "greetings.hello"


def test_generate_unit_exercises_retries_then_succeeds(monkeypatch):
    from backend import hf_client as hf_client_module

    responses = iter(["not json", _VALID_EXERCISE_JSON])

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return next(responses)

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    unit = units_for_level(CEFRLevel.A1)[1]
    exercises = asyncio.run(generators.generate_unit_exercises(unit, "English", "Spanish"))
    assert len(exercises) == 1


def test_generate_unit_exercises_raises_after_exhausting_retries(monkeypatch):
    from backend import hf_client as hf_client_module

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "still not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    unit = units_for_level(CEFRLevel.A1)[1]
    try:
        asyncio.run(generators.generate_unit_exercises(unit, "English", "Spanish"))
        assert False, "expected GenerationError"
    except generators.GenerationError:
        pass


def test_generate_unit_exercises_never_personalizes(monkeypatch):
    """Build-time generation must always use interests=[]/recent_mistakes=[]
    — content belongs to the course, not the user."""
    from backend import hf_client as hf_client_module

    captured_prompts = []

    async def capture(messages, max_tokens=1000, temperature=0.7):
        captured_prompts.append(messages[-1]["content"])
        return _VALID_EXERCISE_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", capture)
    unit = units_for_level(CEFRLevel.A1)[1]
    asyncio.run(generators.generate_unit_exercises(unit, "English", "Spanish"))
    # No per-user hint clause should appear when there's nothing to weave in.
    assert "recently struggled with" not in captured_prompts[0]


def test_build_flashcards_dedupes_and_omits_ipa():
    exercises = [
        _make_exercise(vocab_key="a", target_text="hello"),
        _make_exercise(vocab_key="a", target_text="hello (dup)"),  # same vocab_key, skipped
        _make_exercise(vocab_key="b", target_text="goodbye"),
        _make_exercise(vocab_key="", target_text="no key"),  # no vocab_key, skipped
    ]
    cards = generators.build_flashcards(exercises)
    assert [c["vocab_key"] for c in cards] == ["a", "b"]
    assert all("ipa" not in c for c in cards)  # never fabricates unverified IPA


def test_wrap_with_teaching_intros_delegates():
    ex = _make_exercise()
    result = generators.wrap_with_teaching_intros([ex])
    assert len(result) == 2
    assert result[0].type == ExerciseType.VOCAB_INTRO


# ── Build pipeline ───────────────────────────────────────────────────────


def test_build_language_level_persists_content_and_flashcards_and_sets_version(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return _VALID_EXERCISE_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    # Limit scope to one unit so the test doesn't need one response per unit.
    monkeypatch.setattr(
        "backend.language_library.build.curriculum.units_for_level",
        lambda level: units_for_level(level)[1:2],
    )
    store = FileSystemAcademyStore(str(tmp_path))

    report = asyncio.run(build.build_language_level(store, "English", "Spanish", CEFRLevel.A1, "v1"))
    assert report.ok
    assert report.units_built == 1
    assert store.get_latest_version("English:Spanish", "A1") == "v1"

    unit_id = units_for_level(CEFRLevel.A1)[1].id
    content = store.load_course_asset("English:Spanish", "A1", unit_id, "content")
    assert content[0]["type"] == "vocab_intro"  # teaching intro prepended
    assert content[1]["vocab_key"] == "greetings.hello"
    flashcards = store.load_course_asset("English:Spanish", "A1", unit_id, "flashcards")
    assert flashcards[0]["vocab_key"] == "greetings.hello"


def test_build_language_level_is_resumable(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    monkeypatch.setattr(
        "backend.language_library.build.curriculum.units_for_level",
        lambda level: units_for_level(level)[1:2],
    )
    unit_id = units_for_level(CEFRLevel.A1)[1].id
    store = FileSystemAcademyStore(str(tmp_path))
    store.save_course_asset("English:Spanish", "A1", "v1", unit_id, "content", [{"already": "built"}])

    async def explode(messages, max_tokens=1000, temperature=0.7):
        raise AssertionError("must not regenerate an already-built unit without --force")

    monkeypatch.setattr(hf_client_module.hf_client, "chat", explode)
    report = asyncio.run(build.build_language_level(store, "English", "Spanish", CEFRLevel.A1, "v1", force=False))
    assert report.ok
    assert store.load_course_asset("English:Spanish", "A1", unit_id, "content") == [{"already": "built"}]


def test_build_language_level_records_failure_and_does_not_publish(tmp_path, monkeypatch):
    from backend import hf_client as hf_client_module

    monkeypatch.setattr(
        "backend.language_library.build.curriculum.units_for_level",
        lambda level: units_for_level(level)[1:2],
    )

    async def always_invalid(messages, max_tokens=1000, temperature=0.7):
        return "not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", always_invalid)
    store = FileSystemAcademyStore(str(tmp_path))
    report = asyncio.run(build.build_language_level(store, "English", "Spanish", CEFRLevel.A1, "v1"))
    assert not report.ok
    assert store.get_latest_version("English:Spanish", "A1") is None


def test_next_version_independent_per_pair_and_level():
    class _FakeStore:
        def __init__(self):
            self.versions = {}

        def get_latest_version(self, pair_key, level):
            return self.versions.get((pair_key, level))

    fake = _FakeStore()
    assert build.next_version(fake, "en:es", "A1") == "v1"
    fake.versions[("en:es", "A1")] = "v1"
    assert build.next_version(fake, "en:es", "A1") == "v2"
    assert build.next_version(fake, "en:es", "A2") == "v1"
    assert build.next_version(fake, "ko:es", "A1") == "v1"
