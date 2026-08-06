"""Tests for the audio architecture fix: hf_client.text_to_speech writing
into the permanent, never-evicted audio_store_dir (not the LRU-evicted
cache_dir), routers/audio.py serving it back out with real cache/Range
semantics, routers/content.py's /tts endpoint resolving a URL instead of
streaming bytes, and language_library/build.py pre-generating audio for
every vocab_intro/listen_type exercise at build time.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend import hf_client as hf_client_module
from backend.config import settings
from backend.language_library import build as language_build
from backend.main import app
from backend.models import Exercise, ExerciseType
from conftest import dev_login


def _onboard(client, email: str) -> dict:
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={"display_name": "Audio Test", "native_lang": "English", "target_lang": "Spanish", "level": "A1", "interests": []},
    )
    assert res.status_code == 200
    return res.json()


@pytest.fixture
def isolated_audio_store_dir(tmp_path):
    """Settings is a frozen dataclass — object.__setattr__ is the same
    pattern test_hf_client.py's isolated_cache_dir already uses to override
    a frozen field for a test."""
    original = settings.audio_store_dir
    object.__setattr__(settings, "audio_store_dir", str(tmp_path))
    yield tmp_path
    object.__setattr__(settings, "audio_store_dir", original)


@pytest.fixture
def piper_enabled_in_tests():
    """text_to_speech's Piper tier is deliberately skipped whenever
    settings.testing is set (see conftest.py — LINGUA_TESTING=1 keeps the
    whole suite offline), so it falls through to the real network-bound HF
    MMS tier instead. The two tests using this fixture care specifically
    about text_to_speech's own Piper-tier caching/routing behavior with a
    mocked synthesize(), so they need that guard briefly lifted instead of
    actually hitting the network — every other test in this file exercises
    a caller of text_to_speech (routers/content.py, language_library/
    build.py) and mocks text_to_speech itself instead, same convention
    tests/test_language_library.py already uses for hf_client.chat."""
    original = settings.testing
    object.__setattr__(settings, "testing", False)
    yield
    object.__setattr__(settings, "testing", original)


async def _fake_piper_synthesize(text: str, target_lang: str) -> bytes:
    return f"WAV:{target_lang}:{text}".encode()


def test_text_to_speech_writes_into_audio_store_not_cache_dir(
    monkeypatch, isolated_audio_store_dir, piper_enabled_in_tests, tmp_path
):
    from backend import piper_tts

    monkeypatch.setattr(piper_tts, "synthesize", _fake_piper_synthesize)
    other_cache_dir = tmp_path / "unrelated-media-cache"
    other_cache_dir.mkdir()
    object.__setattr__(settings, "cache_dir", str(other_cache_dir))

    result = asyncio.run(hf_client_module.hf_client.text_to_speech("hola", "es"))
    assert result is not None
    audio, media_type, filename = result
    assert audio == b"WAV:es:hola"
    assert media_type == "audio/wav"
    assert filename.startswith("tts-piper-") and filename.endswith(".wav")
    assert (isolated_audio_store_dir / filename).is_file()
    # Confirms it never touched the (separate, LRU-evictable) cache_dir.
    assert list(other_cache_dir.iterdir()) == []


def test_text_to_speech_cache_hit_skips_synthesis_entirely(
    monkeypatch, isolated_audio_store_dir, piper_enabled_in_tests
):
    from backend import piper_tts

    calls = []

    async def counting_synthesize(text: str, target_lang: str) -> bytes:
        calls.append((text, target_lang))
        return b"first-call-bytes"

    monkeypatch.setattr(piper_tts, "synthesize", counting_synthesize)

    first = asyncio.run(hf_client_module.hf_client.text_to_speech("hola", "es"))
    second = asyncio.run(hf_client_module.hf_client.text_to_speech("hola", "es"))

    assert first == second
    assert len(calls) == 1  # second call was a pure cache hit


def test_audio_router_serves_cached_file_with_immutable_cache_control(isolated_audio_store_dir):
    (isolated_audio_store_dir / "tts-piper-abc123.wav").write_bytes(b"RIFF....fake wav")

    with TestClient(app) as client:
        res = client.get("/api/audio/tts-piper-abc123.wav")
        assert res.status_code == 200
        assert res.content == b"RIFF....fake wav"
        assert res.headers["content-type"] == "audio/wav"
        assert "immutable" in res.headers["cache-control"]


def test_audio_router_404s_for_missing_file(isolated_audio_store_dir):
    with TestClient(app) as client:
        res = client.get("/api/audio/tts-piper-doesnotexist.wav")
        assert res.status_code == 404


@pytest.mark.parametrize("filename", ["tts-piper-abc.exe", "no-extension", "tts-piper-has spaces.wav"])
def test_audio_router_rejects_names_that_dont_match_the_generated_pattern(filename):
    # Only same-segment weirdness reaches the handler at all: FastAPI's
    # default {filename} path converter is a single path segment, so an
    # actual "/" (encoded or not) in the traversal attempt never matches
    # this route in the first place (Starlette 404s it before _FILENAME_RE
    # even runs) — a stronger guarantee than the regex, verified separately
    # below. This covers the filenames that *do* reach the handler.
    with TestClient(app) as client:
        res = client.get(f"/api/audio/{filename}")
        assert res.status_code == 400


@pytest.mark.parametrize("attempt", ["../../../etc/passwd", "..%2f..%2fetc%2fpasswd"])
def test_audio_router_traversal_attempts_never_match_the_route(attempt):
    with TestClient(app) as client:
        res = client.get(f"/api/audio/{attempt}")
        # Never a 200 with file content — whether that's a 404 (route
        # didn't match, single-segment converter) or 400 (reached the
        # handler and failed _FILENAME_RE) doesn't matter to a caller;
        # what matters is nothing outside audio_store_dir is ever returned.
        assert res.status_code != 200


def test_tts_endpoint_returns_a_url_not_raw_bytes(monkeypatch, isolated_audio_store_dir):
    async def fake_text_to_speech(text, target_lang, voice_description=None, persona_id=None):
        return f"WAV:{target_lang}:{text}".encode(), "audio/wav", "tts-piper-deadbeef.wav"

    monkeypatch.setattr(hf_client_module.hf_client, "text_to_speech", fake_text_to_speech)
    (isolated_audio_store_dir / "tts-piper-deadbeef.wav").write_bytes(b"WAV:es:hola")

    with TestClient(app) as client:
        _onboard(client, "tts-url@example.com")
        res = client.post("/api/content/tts", json={"text": "hola", "target_lang": "es"})
        assert res.status_code == 200
        body = res.json()
        assert body["url"] == "/api/audio/tts-piper-deadbeef.wav"

        # The URL is actually fetchable and serves the same bytes.
        audio_res = client.get(body["url"])
        assert audio_res.status_code == 200
        assert audio_res.content == b"WAV:es:hola"


def test_tts_endpoint_503s_when_every_provider_is_exhausted(monkeypatch):
    async def fake_text_to_speech(text, target_lang, voice_description=None, persona_id=None):
        return None

    monkeypatch.setattr(hf_client_module.hf_client, "text_to_speech", fake_text_to_speech)

    with TestClient(app) as client:
        _onboard(client, "tts-exhausted@example.com")
        res = client.post("/api/content/tts", json={"text": "hola", "target_lang": "es"})
        assert res.status_code == 503


def _fake_text_to_speech_factory():
    calls = []

    async def fake(text, target_lang, voice_description=None, persona_id=None):
        calls.append(text)
        # Padded past validate_audio_bytes's minimum-size floor (see
        # language_library/build.py) — a handful of raw bytes wouldn't
        # pass as a real WAV/FLAC/MP3 payload and _attach_audio would
        # (correctly) discard it rather than set audio_url from it.
        return f"WAV:{text}".encode().ljust(128, b"\0"), "audio/wav", f"tts-fake-{len(calls)}.wav"

    return fake, calls


def test_build_pipeline_attaches_audio_only_to_audible_exercise_types(monkeypatch):
    fake, calls = _fake_text_to_speech_factory()
    monkeypatch.setattr(hf_client_module.hf_client, "text_to_speech", fake)

    exercises = [
        Exercise(
            id="ex-0", type=ExerciseType.VOCAB_INTRO, prompt="p", target_text="hola",
            correct_answer="hola", audio_text="hola",
        ),
        Exercise(
            id="ex-1", type=ExerciseType.MULTIPLE_CHOICE, prompt="p", target_text="hola",
            correct_answer="hola", options=["hola", "adios"],
        ),
        Exercise(
            id="ex-2", type=ExerciseType.LISTEN_TYPE, prompt="p", target_text="adios",
            correct_answer="adios", audio_text="adios",
        ),
    ]

    asyncio.run(language_build._attach_audio(exercises, "es", "es:en", "unit-0"))

    assert exercises[0].audio_url == "/api/audio/tts-fake-1.wav"
    assert exercises[1].audio_url == ""  # multiple_choice never gets a button in the UI
    assert exercises[2].audio_url == "/api/audio/tts-fake-2.wav"
    assert calls == ["hola", "adios"]  # only the two audible exercises were synthesized


def test_build_pipeline_skips_exercises_that_already_have_audio(monkeypatch):
    fake, calls = _fake_text_to_speech_factory()
    monkeypatch.setattr(hf_client_module.hf_client, "text_to_speech", fake)

    exercises = [
        Exercise(
            id="ex-0", type=ExerciseType.VOCAB_INTRO, prompt="p", target_text="hola",
            correct_answer="hola", audio_text="hola", audio_url="/api/audio/already-there.wav",
        ),
    ]

    asyncio.run(language_build._attach_audio(exercises, "es", "es:en", "unit-0"))

    assert exercises[0].audio_url == "/api/audio/already-there.wav"
    assert calls == []


def test_build_pipeline_publishes_unit_even_if_audio_synthesis_fails(monkeypatch):
    async def failing_synthesize(*args, **kwargs):
        return None

    monkeypatch.setattr(hf_client_module.hf_client, "text_to_speech", failing_synthesize)

    exercises = [
        Exercise(
            id="ex-0", type=ExerciseType.VOCAB_INTRO, prompt="p", target_text="hola",
            correct_answer="hola", audio_text="hola",
        ),
    ]

    # Must not raise — a failed audio synthesis degrades to no audio_url,
    # it never blocks the unit's text content from publishing.
    asyncio.run(language_build._attach_audio(exercises, "es", "es:en", "unit-0"))
    assert exercises[0].audio_url == ""
