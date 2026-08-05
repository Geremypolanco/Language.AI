"""Tests for the AI orchestration layer (backend/ai/) — the AIOrchestrator
facade, its per-task routers, the model registry, and the offline audio
asset pipeline. Mocks the underlying hf_client/image_search calls (never
touches the network) and drives async code via asyncio.run(), matching the
rest of this suite's style (see e.g. tests/test_academy_library.py)."""

from __future__ import annotations

import asyncio
import os

import pytest

from backend import image_search, personas
from backend.ai import ai_orchestrator, asset_pipeline
from backend.ai.registry import AITask, chain_for
from backend.ai.routers.embeddings import EmbeddingRouter
from backend.ai.voices import voice_profile_for_persona
from backend.config import settings


@pytest.fixture
def isolated_audio_assets_dir(tmp_path):
    """Frozen-dataclass override, same pattern as test_hf_client.py's
    isolated_cache_dir — points the permanent audio-asset store at a
    throwaway directory."""
    original = settings.audio_assets_dir
    object.__setattr__(settings, "audio_assets_dir", str(tmp_path))
    yield
    object.__setattr__(settings, "audio_assets_dir", original)


# ── Registry ──────────────────────────────────────────────────────────────


def test_registry_has_a_chain_for_every_task():
    for task in AITask:
        chain = chain_for(task)
        assert chain, f"{task} has no registered models"
        assert chain[0].tier == "primary"


def test_embedding_registry_points_at_bge_m3():
    chain = chain_for(AITask.EMBEDDING)
    assert chain[0].model_id == "BAAI/bge-m3"
    assert chain[0].provider == "huggingface"


# ── LLMRouter ─────────────────────────────────────────────────────────────


def test_llm_router_delegates_to_hf_client_chat(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_chat(messages, max_tokens=1000, temperature=0.7):
        return "mocked reply"

    monkeypatch.setattr(hf_client_module.hf_client, "chat", fake_chat)
    reply = asyncio.run(ai_orchestrator.llm.chat([{"role": "user", "content": "hola"}]))
    assert reply == "mocked reply"


def test_llm_router_stream_chat_yields_chunks(monkeypatch):
    from backend import hf_client as hf_client_module

    async def fake_stream(messages, max_tokens=1000, temperature=0.7):
        for chunk in ("Hola", " mundo"):
            yield chunk

    monkeypatch.setattr(hf_client_module.hf_client, "stream_chat", fake_stream)

    async def collect():
        return [c async for c in ai_orchestrator.llm.stream_chat([{"role": "user", "content": "hi"}])]

    assert asyncio.run(collect()) == ["Hola", " mundo"]


# ── EmbeddingRouter ───────────────────────────────────────────────────────


def test_cosine_similarity_identical_vectors_is_one():
    assert EmbeddingRouter.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert EmbeddingRouter.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_handles_empty_or_mismatched_vectors():
    assert EmbeddingRouter.cosine_similarity([], [1.0]) == 0.0
    assert EmbeddingRouter.cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_semantic_rank_orders_by_similarity(monkeypatch):
    from backend import hf_client as hf_client_module

    # A tiny fake embedding space: "query" is close to candidate 1, far from 0.
    vectors = {
        "cats are great": [1.0, 0.0],
        "a story about cats": [0.9, 0.1],
        "a story about airplanes": [0.0, 1.0],
    }

    async def fake_embed(text):
        return vectors[text]

    monkeypatch.setattr(hf_client_module.hf_client, "embed_text", fake_embed)
    ranked = asyncio.run(
        ai_orchestrator.embeddings.semantic_rank(
            "cats are great", ["a story about airplanes", "a story about cats"], top_k=5
        )
    )
    assert [i for i, _ in ranked] == [1, 0]  # "cats" candidate (index 1) ranks first


def test_semantic_rank_returns_empty_when_embeddings_unavailable():
    # settings.testing is set for the whole suite (see conftest.py), so
    # hf_client.embed_text short-circuits to None without any network call.
    ranked = asyncio.run(ai_orchestrator.embeddings.semantic_rank("query", ["a", "b"]))
    assert ranked == []


# ── SpeechRouter (offline asset pipeline) ────────────────────────────────


def test_synthesize_asset_returns_none_for_empty_text():
    assert asyncio.run(ai_orchestrator.speech.synthesize_asset("ns", "key", "   ", "en")) is None


def test_synthesize_asset_writes_and_reuses_a_permanent_file(monkeypatch, isolated_audio_assets_dir):
    calls = []

    async def fake_synthesize(text, target_lang, voice_description=None, persona_id=None):
        calls.append(text)
        return b"fake-audio-bytes", "audio/wav"

    monkeypatch.setattr(ai_orchestrator.speech, "synthesize", fake_synthesize)

    url1 = asyncio.run(ai_orchestrator.speech.synthesize_asset("vocab", "hola", "hola", "es"))
    assert url1 is not None
    assert url1.startswith("/audio-assets/vocab/")
    assert url1.endswith(".wav")

    on_disk = os.path.join(settings.audio_assets_dir, "vocab", os.path.basename(url1))
    assert os.path.exists(on_disk)
    with open(on_disk, "rb") as f:
        assert f.read() == b"fake-audio-bytes"

    # A second call with the exact same inputs must not re-synthesize.
    url2 = asyncio.run(ai_orchestrator.speech.synthesize_asset("vocab", "hola", "hola", "es"))
    assert url2 == url1
    assert calls == ["hola"]


def test_synthesize_asset_returns_none_when_every_provider_fails(monkeypatch, isolated_audio_assets_dir):
    async def fake_synthesize(text, target_lang, voice_description=None, persona_id=None):
        return None

    monkeypatch.setattr(ai_orchestrator.speech, "synthesize", fake_synthesize)
    assert asyncio.run(ai_orchestrator.speech.synthesize_asset("vocab", "adios", "adios", "es")) is None


# ── VisionRouter ──────────────────────────────────────────────────────────


def test_illustrate_tries_real_photos_before_ai_generation(monkeypatch):
    calls = []

    async def fake_search_image(prompt):
        calls.append("google")
        return None

    async def fake_search_wikimedia(prompt):
        calls.append("wikimedia")
        return b"real-photo-bytes"

    async def fake_generate_image(prompt):
        calls.append("ai-generate")
        return b"ai-bytes"

    monkeypatch.setattr(image_search, "search_image", fake_search_image)
    monkeypatch.setattr(image_search, "search_wikimedia_commons", fake_search_wikimedia)
    monkeypatch.setattr(ai_orchestrator.vision, "generate_image", fake_generate_image)

    result = asyncio.run(ai_orchestrator.vision.illustrate("a red apple"))
    assert result == b"real-photo-bytes"
    assert calls == ["google", "wikimedia"]  # AI generation never called — a real photo was found


def test_illustrate_skip_photo_search_goes_straight_to_ai_generation(monkeypatch):
    async def fail_if_called(prompt):
        raise AssertionError("photo search should have been skipped")

    async def fake_generate_image(prompt):
        return b"ai-bytes"

    monkeypatch.setattr(image_search, "search_image", fail_if_called)
    monkeypatch.setattr(ai_orchestrator.vision, "generate_image", fake_generate_image)

    result = asyncio.run(ai_orchestrator.vision.illustrate("a crafted portrait prompt", skip_photo_search=True))
    assert result == b"ai-bytes"


# ── Voice profiles ────────────────────────────────────────────────────────


def test_voice_profile_derives_structured_fields_from_persona():
    elena = personas.get_core_teacher("core-elena")
    profile = voice_profile_for_persona(elena)
    assert profile.persona_id == "core-elena"
    assert profile.rate == "slow"  # "deliberate, moderate pace" / "measured" in her description
    assert "crisp" in profile.style_tags
    assert profile.sampling_temperature == elena.sampling_temperature


def test_every_core_teacher_has_a_derivable_voice_profile():
    for teacher in personas.all_core_teachers():
        profile = voice_profile_for_persona(teacher)
        assert profile.rate in ("slow", "moderate", "fast")
        assert profile.pitch in ("low", "moderate", "high")


# ── Offline asset pipeline ────────────────────────────────────────────────


def test_add_glossary_audio_sets_url_per_term(monkeypatch):
    async def fake_synthesize_asset(namespace, key, text, target_lang, **kwargs):
        return f"/audio-assets/{namespace}/{key}.wav"

    monkeypatch.setattr(ai_orchestrator.speech, "synthesize_asset", fake_synthesize_asset)

    glossary = {"terms": [{"term": "algoritmo", "definition": "..."}, {"term": "", "definition": "skipped"}]}
    result = asyncio.run(asset_pipeline.add_glossary_audio("glossary:cs:BACHELOR", "es", glossary))
    assert result["terms"][0]["audio_url"] == "/audio-assets/glossary:cs:BACHELOR/algoritmo.wav"
    assert "audio_url" not in result["terms"][1]  # empty term text is skipped entirely


def test_add_glossary_audio_is_best_effort_on_failure(monkeypatch):
    async def raising_synthesize_asset(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ai_orchestrator.speech, "synthesize_asset", raising_synthesize_asset)

    glossary = {"terms": [{"term": "algoritmo", "definition": "..."}]}
    result = asyncio.run(asset_pipeline.add_glossary_audio("glossary:cs:BACHELOR", "es", glossary))
    assert result["terms"][0]["audio_url"] is None  # logged, not raised


def test_add_flashcard_audio_prefers_audio_text_over_target_text(monkeypatch):
    seen = {}

    async def fake_synthesize_asset(namespace, key, text, target_lang, **kwargs):
        seen["text"] = text
        return "/audio-assets/x/y.wav"

    monkeypatch.setattr(ai_orchestrator.speech, "synthesize_asset", fake_synthesize_asset)

    flashcards = [{"vocab_key": "a1.hola", "target_text": "hola", "audio_text": "¡Hola!"}]
    result = asyncio.run(asset_pipeline.add_flashcard_audio("flashcards:en:es:A1:unit-0", "es", flashcards))
    assert seen["text"] == "¡Hola!"
    assert result[0]["audio_url"] == "/audio-assets/x/y.wav"
