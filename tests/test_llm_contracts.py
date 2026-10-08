"""Tests for backend/llm_contracts — the U2/U3/U5 anti-hallucination layer.

U2: every structured LLM output is validated against a pydantic contract;
invalid output is retried (max 3, exponential backoff) and then routed to
the dead-letter queue — never invented, never shown to the learner.
U3: conversion of validated contracts into domain objects is pure and
deterministic. U5: facts carry `fuente:id` provenance or they don't ship.

No test here touches the network: validate_or_retry is exercised with
fakes, and hf_client.chat is monkeypatched the same way
test_hf_client.py already does.
"""

import asyncio
import json
import os

import pytest
from pydantic import ValidationError

from backend import hf_client as hf_client_module
from backend.llm_contracts import (
    EXERCISE_LIST,
    NEWS_LIST,
    NON_EMPTY_TEXT,
    RECOMMENDATION_LIST,
    REVIEW_EXERCISE_LIST,
    AssignmentGrade,
    CitationError,
    DeadLetterEntry,
    DeadLetterQueue,
    ExerciseJSON,
    NewsArticle,
    OpenAnswerGrade,
    RecommendationItem,
    ReviewExerciseJSON,
    dead_letters,
    grounding_citations,
    is_valid_citation,
    require_citations,
    source_to_citation,
    validate_or_retry,
)
from backend.hf_client import _exercise_from_contract, _review_exercise_from_contract


def run(coro):
    return asyncio.run(coro)


# ── validate_or_retry ──────────────────────────────────────────────────


def test_valid_output_passes_first_try_with_no_retry():
    calls = []

    async def fn():
        calls.append(1)
        return [{"type": "multiple_choice", "target_text": "hola", "vocab_key": "k1"}]

    ok, data = run(validate_or_retry(fn, EXERCISE_LIST, schema_name="ExerciseList", base_delay_s=0))
    assert ok is True
    assert len(calls) == 1
    assert data[0].target_text == "hola"
    assert isinstance(data[0], ExerciseJSON)


def test_invalid_then_valid_retries_and_succeeds():
    calls = []

    async def fn():
        calls.append(1)
        if len(calls) < 3:
            return [{"type": "not_a_real_type", "target_text": "hola", "vocab_key": "k1"}]
        return [{"type": "multiple_choice", "target_text": "hola", "vocab_key": "k1"}]

    ok, data = run(validate_or_retry(fn, EXERCISE_LIST, schema_name="ExerciseList", base_delay_s=0))
    assert ok is True
    assert len(calls) == 3
    assert data[0].type.value == "multiple_choice"


def test_persistent_invalid_output_dead_letters_after_exactly_3_attempts(tmp_path):
    queue = DeadLetterQueue(directory=str(tmp_path / "dlq"))
    calls = []

    async def fn():
        calls.append(1)
        return [{"type": "multiple_choice", "target_text": "", "vocab_key": "k1"}]  # empty target_text

    ok, data = run(
        validate_or_retry(
            fn, EXERCISE_LIST, schema_name="ExerciseList",
            base_delay_s=0, queue=queue, context={"unit": "u1"},
        )
    )
    assert ok is False
    assert data is None
    assert len(calls) == 3  # max_retries=3, not more, not fewer
    entries = queue.list()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.schema == "ExerciseList"
    assert entry.attempts == 3
    assert entry.context == {"unit": "u1"}
    assert any("target_text" in e for e in entry.errors)


def test_raising_fn_counts_as_failed_attempt_and_dead_letters(tmp_path):
    queue = DeadLetterQueue(directory=str(tmp_path / "dlq"))
    calls = []

    async def fn():
        calls.append(1)
        raise RuntimeError("provider down")

    ok, data = run(
        validate_or_retry(fn, EXERCISE_LIST, schema_name="ExerciseList", base_delay_s=0, queue=queue)
    )
    assert (ok, data) == (False, None)
    assert len(calls) == 3
    entry = queue.list()[0]
    assert any("RuntimeError" in e and "provider down" in e for e in entry.errors)


def test_never_invents_data_to_satisfy_schema(tmp_path):
    """The whole point of U2: a wrong-shaped payload must come back as
    (False, None) — never padded with defaults into a fake success."""
    queue = DeadLetterQueue(directory=str(tmp_path / "dlq"))

    async def fn():
        return {"this": "is not a list at all"}

    ok, data = run(
        validate_or_retry(fn, EXERCISE_LIST, schema_name="ExerciseList", base_delay_s=0, queue=queue)
    )
    assert ok is False
    assert data is None


def test_accepts_plain_basemodel_class_as_schema(tmp_path):
    queue = DeadLetterQueue(directory=str(tmp_path / "dlq"))

    async def fn():
        return {"grade": "Bien", "feedback": "Buen trabajo."}

    ok, data = run(
        validate_or_retry(fn, AssignmentGrade, schema_name="AssignmentGrade", base_delay_s=0, queue=queue)
    )
    assert ok is True
    assert data.grade == "Bien"


def test_sync_fn_is_supported():
    ok, data = run(
        validate_or_retry(lambda: "hello", NON_EMPTY_TEXT, schema_name="T", base_delay_s=0)
    )
    assert ok is True
    assert data.root == "hello"


# ── DeadLetterQueue ────────────────────────────────────────────────────


def test_dead_letter_entry_round_trip():
    entry = DeadLetterEntry.new(schema="S", errors=["e1"], attempts=2, context={"a": "b"})
    restored = DeadLetterEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored.id == entry.id
    assert restored.schema == "S"
    assert restored.errors == ["e1"]
    assert restored.attempts == 2
    assert restored.context == {"a": "b"}


def test_queue_persists_jsonl_and_reloads(tmp_path):
    d = str(tmp_path / "dlq")
    q1 = DeadLetterQueue(directory=d)
    q1.push(DeadLetterEntry.new(schema="A", errors=["x"], attempts=1))
    q1.push(DeadLetterEntry.new(schema="B", errors=["y"], attempts=3))

    assert os.path.exists(os.path.join(d, "dead_letters.jsonl"))

    q2 = DeadLetterQueue(directory=d)  # new instance reloads the file
    assert [e.schema for e in q2.list()] == ["B", "A"]  # newest first


def test_queue_clear(tmp_path):
    q = DeadLetterQueue(directory=str(tmp_path / "dlq"))
    q.push(DeadLetterEntry.new(schema="A", errors=["x"], attempts=1))
    q.clear()
    assert len(q) == 0
    assert q.list() == []


# ── Schemas ────────────────────────────────────────────────────────────


def test_exercise_contract_rejects_unknown_type():
    with pytest.raises(ValidationError):
        EXERCISE_LIST.validate_python([{"type": "telepathy", "target_text": "x", "vocab_key": "k"}])


def test_exercise_contract_rejects_empty_target_text():
    with pytest.raises(ValidationError):
        EXERCISE_LIST.validate_python([{"type": "multiple_choice", "target_text": "", "vocab_key": "k"}])


def test_exercise_contract_requires_vocab_key():
    with pytest.raises(ValidationError):
        EXERCISE_LIST.validate_python([{"type": "multiple_choice", "target_text": "hola"}])


def test_review_list_rejects_empty_batch():
    with pytest.raises(ValidationError):
        REVIEW_EXERCISE_LIST.validate_python([])


def test_review_item_allows_partial_fields():
    items = REVIEW_EXERCISE_LIST.validate_python([{"type": "translate_to_native"}])
    assert items[0].target_text == ""  # caller fills from its own snapshot


def test_open_answer_grade_parses_string_false_correctly():
    """Regression: the old code did bool(data.get("passed")), and
    bool("false") is True in Python — a model writing "false" graded the
    answer as PASSED. The contract must parse it to False."""
    g = OpenAnswerGrade.model_validate({"passed": "false", "feedback": "x"})
    assert g.passed is False
    g2 = OpenAnswerGrade.model_validate({"passed": "true", "feedback": "x"})
    assert g2.passed is True


def test_open_answer_grade_rejects_missing_feedback():
    with pytest.raises(ValidationError):
        OpenAnswerGrade.model_validate({"passed": True})


def test_assignment_grade_rejects_empty_grade():
    with pytest.raises(ValidationError):
        AssignmentGrade.model_validate({"grade": "", "feedback": "x"})


def test_recommendation_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        RecommendationItem.model_validate(
            {"kind": "movie", "title": "T", "creator": "C", "reason": "R"}
        )


def test_recommendation_list_rejects_empty():
    with pytest.raises(ValidationError):
        RECOMMENDATION_LIST.validate_python([])


def test_news_list_accepts_empty_translation_but_rejects_empty_batch():
    articles = NEWS_LIST.validate_python([{"title": "T", "content": "C", "translation": ""}])
    assert articles[0].translation == ""
    with pytest.raises(ValidationError):
        NEWS_LIST.validate_python([])


def test_non_empty_text_rejects_empty_and_whitespace():
    NON_EMPTY_TEXT.validate_python("hello")
    with pytest.raises(ValidationError):
        NON_EMPTY_TEXT.validate_python("")
    with pytest.raises(ValidationError):
        NON_EMPTY_TEXT.validate_python("   \n  ")


def test_news_article_is_bounded():
    with pytest.raises(ValidationError):
        NewsArticle.model_validate({"title": "T", "content": "C" * 2000, "translation": ""})


# ── U3 deterministic converters ────────────────────────────────────────


def test_exercise_from_contract_applies_deterministic_defaults():
    item = ExerciseJSON.model_validate(
        {"type": "multiple_choice", "target_text": "el gato", "vocab_key": "pets.cat"}
    )
    ex = _exercise_from_contract(item, 4)
    assert ex.id == "ex-4-pets.cat"  # id assigned by caller, never the model
    assert ex.correct_answer == "el gato"  # falls back to target_text
    assert ex.audio_text == "el gato"
    assert ex.vocab_key == "pets.cat"


def test_review_exercise_from_contract_forces_identity_from_snapshot():
    item = ReviewExerciseJSON.model_validate({"type": "fill_blank", "prompt": "Completa."})
    src = {"vocab_key": "food.bread", "target_text": "el pan", "native_text": "bread"}
    ex = _review_exercise_from_contract(item, src)
    assert ex.id == "review-food.bread"
    assert ex.vocab_key == "food.bread"
    assert ex.target_text == "el pan"  # model's omission → snapshot value
    assert ex.correct_answer == "bread"


# ── U5 citations ───────────────────────────────────────────────────────


def test_citation_format():
    assert is_valid_citation("wikipedia:Photosynthesis")
    assert is_valid_citation("arxiv:quantum-tunneling-1901.00001")
    assert not is_valid_citation("Wikipedia:Photosynthesis")  # namespace must be lowercase
    assert not is_valid_citation("just-a-string")
    assert not is_valid_citation("a:")


def test_source_to_citation():
    assert source_to_citation("intake.leadsPerMonth") == "intake:leadsPerMonth"
    assert source_to_citation("crm:lead-4821") == "crm:lead-4821"


def test_grounding_citations_derives_from_rag_text():
    context = (
        "Real, reference material from Wikipedia (for grounding):\n"
        "- Photosynthesis: the process by which plants convert light…\n"
        "- Mitochondrion: an organelle that generates energy…\n"
        "- Photosynthesis: the process by which plants convert light…\n"  # duplicate
        "some prose without a dash prefix is ignored\n"
    )
    assert grounding_citations(context, "wikipedia") == [
        "wikipedia:Photosynthesis",
        "wikipedia:Mitochondrion",
    ]


def test_require_citations_throws_without_provenance():
    with pytest.raises(CitationError):
        require_citations([{"label": "finding-1", "citations": ["wikipedia:A"]}])
    with pytest.raises(CitationError):
        require_citations(
            [{"label": "finding-1", "citations": ["wikipedia:A", "bad citation", "arxiv:B"]}]
        )
    # 3 valid citations pass
    require_citations(
        [{"label": "finding-1", "citations": ["wikipedia:A", "arxiv:B", "intake:q7"]}]
    )


# ── End-to-end through hf_client (chat monkeypatched, no network) ──────


def _dlq_size_before():
    return len(dead_letters)


def test_grade_open_answer_string_false_grades_as_failed(monkeypatch):
    """End-to-end proof the truthy bug is dead: model says "false" → fail."""

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return '{"passed": "false", "feedback": "casi"}'

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    before = _dlq_size_before()
    passed, feedback = run(
        hf_client_module.hf_client.grade_open_answer("Q?", "rubric", "answer", "es")
    )
    assert passed is False
    assert feedback == "casi"
    assert len(dead_letters) == before  # valid output → no dead letter


def test_grade_open_answer_garbage_dead_letters_and_fails_closed(monkeypatch):
    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return "definitely not json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    before = _dlq_size_before()
    passed, feedback = run(
        hf_client_module.hf_client.grade_open_answer("Q?", "rubric", "answer", "es")
    )
    assert passed is False  # fail-closed, never silently correct
    assert "No se pudo calificar" in feedback
    assert len(dead_letters) == before + 1
    assert dead_letters.list()[0].schema == "OpenAnswerGrade"


def test_conversation_reply_empty_string_uses_fallback_and_dead_letters(monkeypatch):
    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return "   "

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    before = _dlq_size_before()
    reply = run(hf_client_module.hf_client.conversation_reply("sys", []))
    assert "no se pudo generar" in reply
    assert len(dead_letters) == before + 1
    assert dead_letters.list()[0].schema == "TutorReply"


def test_generate_exercises_invalid_json_dead_letters_and_serves_fallback(monkeypatch, tmp_path):
    """Invalid JSON 3× → dead-letter + the honest offline fallback (which
    labels itself as offline), never a crash, never invented exercises."""
    from backend.config import settings
    from backend.curriculum import LessonRequest, units_for_level
    from backend.models import CEFRLevel

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return "[[[not valid json"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    original = settings.cache_dir
    object.__setattr__(settings, "cache_dir", str(tmp_path))
    try:
        unit = units_for_level(CEFRLevel.A1)[0]
        req = LessonRequest(
            unit=unit, native_lang="es", target_lang="en", interests=[], recent_mistakes=[]
        )
        before = _dlq_size_before()
        exercises = run(hf_client_module.hf_client.generate_exercises(req))
    finally:
        object.__setattr__(settings, "cache_dir", original)

    assert len(exercises) > 0  # fallback served
    assert any("Sin conexión" in e.prompt for e in exercises)  # honestly labeled
    assert len(dead_letters) == before + 1
    assert dead_letters.list()[0].schema == "ExerciseList"


def test_generate_exercises_valid_contract_output_is_cached_and_served(monkeypatch, tmp_path):
    from backend.config import settings
    from backend.curriculum import LessonRequest, units_for_level
    from backend.models import CEFRLevel

    payload = json.dumps(
        [
            {
                "type": "multiple_choice",
                "prompt": "Elige.",
                "target_text": "el gato",
                "native_text": "the cat",
                "options": ["el gato", "el perro"],
                "correct_answer": "el gato",
                "image_prompt": "a cat",
                "audio_text": "el gato",
                "vocab_key": "pets.cat",
            }
        ]
    )
    calls = []

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        calls.append(1)
        return payload

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    original = settings.cache_dir
    object.__setattr__(settings, "cache_dir", str(tmp_path))
    try:
        unit = units_for_level(CEFRLevel.A1)[0]
        req = LessonRequest(
            unit=unit, native_lang="es", target_lang="en", interests=[], recent_mistakes=[]
        )
        before = _dlq_size_before()
        exercises = run(hf_client_module.hf_client.generate_exercises(req))
    finally:
        object.__setattr__(settings, "cache_dir", original)

    assert len(dead_letters) == before  # no dead letter on success
    # teaching-intro card prepended + the graded exercise
    assert exercises[0].type.value == "vocab_intro"
    assert exercises[1].target_text == "el gato"
    assert exercises[1].correct_answer == "el gato"
    assert calls == [1]
