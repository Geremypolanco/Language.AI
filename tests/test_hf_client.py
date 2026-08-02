"""Unit tests for _HFGuard, the Hugging Face rate/budget guard in
hf_client.py (see its docstring for why it exists: HF is the one AI tier
in this app with a real credit-limited budget, and the only one used as a
last-resort fallback across four different call sites — chat, STT, TTS,
video). Tests the guard's pure state machine directly, without touching
the network, so they stay fast and deterministic."""

import asyncio
import json
import os

import pytest

from backend import hf_client as hf_client_module
from backend.config import settings
from backend.curriculum import ALPHABET_TOPIC, LessonRequest, units_for_level
from backend.hf_client import _HFGuard, _with_teaching_intros
from backend.models import CEFRLevel, Exercise, ExerciseType


@pytest.fixture
def isolated_cache_dir(tmp_path):
    """Settings is a frozen dataclass — object.__setattr__ is the same
    pattern already used elsewhere in this app to override a frozen field
    for a test. Points the media cache at a throwaway directory so this
    test's cache writes never touch (or get confused by leftovers in) the
    real repo-local data/media_cache directory."""
    original = settings.cache_dir
    object.__setattr__(settings, "cache_dir", str(tmp_path))
    yield
    object.__setattr__(settings, "cache_dir", original)


def test_allowed_by_default():
    guard = _HFGuard(daily_budget=1000)
    assert guard.allowed() is True


def test_budget_exhaustion_blocks_further_calls():
    guard = _HFGuard(daily_budget=100)
    guard.record_usage(60)
    assert guard.allowed() is True
    guard.record_usage(60)
    assert guard.allowed() is False


def test_rate_limit_opens_circuit_immediately():
    guard = _HFGuard(daily_budget=1000, cooldown_s=60.0)
    assert guard.allowed() is True
    guard.record_rate_limited()
    assert guard.allowed() is False


def test_circuit_recovers_after_cooldown_elapses():
    # A cooldown of 0 (or negative) means "already elapsed" the instant
    # it's set, since allowed() compares against time.monotonic() at call
    # time — avoids a real sleep() in the test.
    guard = _HFGuard(daily_budget=1000, cooldown_s=-1.0)
    guard.record_rate_limited()
    assert guard.allowed() is True


def test_budget_resets_on_a_new_day():
    guard = _HFGuard(daily_budget=100)
    guard.record_usage(100)
    assert guard.allowed() is False
    # Simulate a day rollover the same way production time passing would.
    guard._budget_day = "2000-01-01"
    assert guard.allowed() is True


def test_with_teaching_intros_precedes_each_graded_exercise_with_a_matching_card():
    # Regression: lessons quizzed a learner on a word cold — a real
    # classroom teaches it first. Each graded exercise must be preceded by
    # a vocab_intro built from that same exercise's own word/translation/
    # audio/image, so the two are always in sync by construction.
    quiz = Exercise(
        id="ex-0-hola",
        type=ExerciseType.MULTIPLE_CHOICE,
        prompt="Elige la traducción correcta.",
        target_text="hello",
        native_text="hola",
        options=["hello", "goodbye", "please"],
        correct_answer="hello",
        image_prompt="a person waving hello",
        audio_text="hello",
        vocab_key="greetings.hello",
    )
    result = _with_teaching_intros([quiz])
    assert len(result) == 2
    intro, graded = result
    assert intro.type == ExerciseType.VOCAB_INTRO
    assert graded is quiz
    assert intro.target_text == quiz.target_text
    assert intro.native_text == quiz.native_text
    assert intro.audio_text == quiz.audio_text
    assert intro.image_prompt == quiz.image_prompt
    assert intro.vocab_key == quiz.vocab_key
    assert intro.options == []  # never graded — nothing to click


def test_with_teaching_intros_skips_free_conversation_prompt():
    conversation = Exercise(
        id="ex-0-chat",
        type=ExerciseType.FREE_CONVERSATION_PROMPT,
        prompt="Cuéntame sobre tu día.",
        target_text="",
        native_text="",
        options=[],
        correct_answer="",
        vocab_key="",
    )
    result = _with_teaching_intros([conversation])
    assert result == [conversation]


_FAKE_EXERCISE_JSON = json.dumps(
    [
        {
            "type": "multiple_choice",
            "prompt": "p",
            "target_text": "t",
            "native_text": "n",
            "options": ["t", "a", "b"],
            "correct_answer": "t",
            "image_prompt": "",
            "audio_text": "t",
            "vocab_key": "k",
        }
    ]
)


def test_alphabet_prompt_version_busts_only_the_alphabet_units_cache(monkeypatch, isolated_cache_dir):
    # Regression: build_exercise_generation_prompt's alphabet-only
    # instructions were fixed (audio_text must never be a bare letter — see
    # curriculum.py's ALPHABET_PROMPT_VERSION), but a disk cache never
    # expires on its own, so the fix alone wouldn't reach a learner who
    # already has a cached (bad) exercise set for that exact unit/language.
    # generate_exercises() must fold ALPHABET_PROMPT_VERSION into the cache
    # key — but ONLY for the alphabet unit, so bumping it doesn't force
    # every other unit's perfectly fine cached content to regenerate too.
    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return _FAKE_EXERCISE_JSON

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)

    alphabet_unit = units_for_level(CEFRLevel.A1)[0]
    other_unit = units_for_level(CEFRLevel.A1)[1]
    assert alphabet_unit.topic == ALPHABET_TOPIC

    alpha_req = LessonRequest(unit=alphabet_unit, native_lang="es", target_lang="ko", interests=[], recent_mistakes=[])
    other_req = LessonRequest(unit=other_unit, native_lang="es", target_lang="ko", interests=[], recent_mistakes=[])

    monkeypatch.setattr(hf_client_module, "ALPHABET_PROMPT_VERSION", "vA")
    asyncio.run(hf_client_module.hf_client.generate_exercises(alpha_req))
    asyncio.run(hf_client_module.hf_client.generate_exercises(other_req))

    from backend.curriculum import resolve_exercise_mix

    def cache_path_for(req, version):
        mix = resolve_exercise_mix(req.unit)
        key = (
            f"{req.unit.id}:{req.unit.topic}:{req.unit.level.value}:{req.target_lang}:{req.native_lang}:"
            f"{','.join(sorted(req.interests))}:{','.join(t.value for t in mix)}:{hf_client_module.EXERCISE_FORMAT_VERSION}"
            f"{':' + version if req.unit.topic == ALPHABET_TOPIC else ''}"
        )
        return hf_client_module.hf_client._cache_path("exercises", key, "json")

    alpha_path_vA = cache_path_for(alpha_req, "vA")
    other_path_vA = cache_path_for(other_req, "vA")
    assert os.path.exists(alpha_path_vA)
    assert os.path.exists(other_path_vA)

    monkeypatch.setattr(hf_client_module, "ALPHABET_PROMPT_VERSION", "vB")
    asyncio.run(hf_client_module.hf_client.generate_exercises(alpha_req))
    asyncio.run(hf_client_module.hf_client.generate_exercises(other_req))

    alpha_path_vB = cache_path_for(alpha_req, "vB")
    other_path_vB = cache_path_for(other_req, "vB")

    assert alpha_path_vA != alpha_path_vB, "bumping the version must change the alphabet unit's cache path"
    assert os.path.exists(alpha_path_vB), "a fresh cache entry must be generated under the new version"
    assert other_path_vA == other_path_vB, "a non-alphabet unit's cache path must be unaffected by the version bump"
