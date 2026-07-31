import asyncio
import json

from backend import hf_client as hf_client_module
from backend.config import settings
from backend.hf_client import hf_client


def _with_hf_configured(fn):
    """settings is a frozen dataclass (see backend/config.py) — object.__setattr__
    is the same escape hatch db.reset_for_tests uses. Restores the original
    token afterward so this doesn't leak into other tests."""
    original = settings.hf_token
    object.__setattr__(settings, "hf_token", "fake-token-for-test")
    try:
        fn()
    finally:
        object.__setattr__(settings, "hf_token", original)


def _with_cache_dir(tmp_path, fn):
    """Points settings.cache_dir at a throwaway pytest tmp_path so ElevenLabs
    tier tests can't collide with real cache files on disk or with each
    other's cached results, then restores the original path."""
    original = settings.cache_dir
    object.__setattr__(settings, "cache_dir", str(tmp_path))
    try:
        fn()
    finally:
        object.__setattr__(settings, "cache_dir", original)


def _with_elevenlabs_configured(voice_map: dict, fn):
    """Same object.__setattr__ escape hatch as _with_hf_configured, for the
    two ElevenLabs settings fields — restores both afterward."""
    original_key = settings.elevenlabs_api_key
    original_map = settings.elevenlabs_voice_map_json
    object.__setattr__(settings, "elevenlabs_api_key", "fake-elevenlabs-key-for-test")
    object.__setattr__(settings, "elevenlabs_voice_map_json", json.dumps(voice_map))
    try:
        fn()
    finally:
        object.__setattr__(settings, "elevenlabs_api_key", original_key)
        object.__setattr__(settings, "elevenlabs_voice_map_json", original_map)


def test_text_to_speech_falls_back_to_parler_space_when_direct_endpoint_errors(monkeypatch):
    async def failing_post(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def fake_space_call(text, description):
        assert description == "a distinctive test voice"
        return b"FAKE_SPACE_AUDIO"

    def run():
        monkeypatch.setattr(hf_client._http, "post", failing_post)
        monkeypatch.setattr(hf_client_module, "_call_parler_space", fake_space_call)
        audio = asyncio.run(
            hf_client.text_to_speech("Hola", "es", voice_description="a distinctive test voice")
        )
        assert audio == b"FAKE_SPACE_AUDIO"

    _with_hf_configured(run)


def test_conversation_reply_parses_the_structured_json_contract(monkeypatch):
    payload = {
        "critique_metrics": {
            "grammar": [{"error": "ser vs estar", "correction": "estoy", "explanation": "temporary state"}],
            "pronunciation": [],
            "comprehension": [],
            "knowledge": [],
        },
        "spoken_response": "¡Casi! Se dice 'estoy cansado' — ¿qué más hiciste hoy?",
    }

    async def fake_chat(messages, max_tokens=500, temperature=0.8):
        assert temperature == 0.55  # Elena's sampling_temperature, passed through
        return json.dumps(payload)

    def run():
        monkeypatch.setattr(hf_client, "chat", fake_chat)
        result = asyncio.run(hf_client.conversation_reply("system prompt", [], temperature=0.55))
        assert result["spoken_response"] == payload["spoken_response"]
        assert result["critique_metrics"]["grammar"][0]["correction"] == "estoy"

    _with_hf_configured(run)


def test_conversation_reply_falls_back_to_raw_text_on_bad_json(monkeypatch):
    async def fake_chat(messages, max_tokens=500, temperature=0.8):
        return "not json at all, just a plain reply"

    def run():
        monkeypatch.setattr(hf_client, "chat", fake_chat)
        result = asyncio.run(hf_client.conversation_reply("system prompt", []))
        assert result["spoken_response"] == "not json at all, just a plain reply"
        assert result["critique_metrics"] == {}

    _with_hf_configured(run)


def test_text_to_speech_falls_back_to_mms_when_every_parler_tier_fails(monkeypatch):
    async def failing_post(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def failing_space_call(text, description):
        return None

    def run():
        monkeypatch.setattr(hf_client._http, "post", failing_post)
        monkeypatch.setattr(hf_client_module, "_call_parler_space", failing_space_call)
        # Both Parler tiers fail, and the MMS fallback hits the same failing
        # post — the whole chain should degrade to None, never raise.
        audio = asyncio.run(hf_client.text_to_speech("Hola", "es", voice_description="a voice"))
        assert audio is None

    _with_hf_configured(run)


def test_preprocess_for_parler_expands_numbers_and_abbreviations():
    out = hf_client_module._preprocess_for_parler("Tengo 12 HF tokens-nuevos", "es")
    assert "12" not in out
    assert "doce" in out
    assert "HF" not in out  # spelled out letter by letter instead
    assert "H F" in out
    assert "-" not in out
    assert out.endswith(".")


def test_preprocess_for_parler_falls_back_to_english_for_unsupported_language():
    out = hf_client_module._preprocess_for_parler("5 items", "zz")
    assert "five" in out


def test_preprocess_for_parler_leaves_existing_trailing_punctuation_alone():
    out = hf_client_module._preprocess_for_parler("Ready?", "en")
    assert out == "Ready?"


def test_text_to_speech_uses_elevenlabs_when_persona_voice_is_mapped(monkeypatch, tmp_path):
    async def fake_elevenlabs_call(text, voice_id):
        assert voice_id == "voice-elena-123"
        return b"FAKE_ELEVENLABS_AUDIO"

    async def unexpected_post(*args, **kwargs):
        raise AssertionError("Parler/MMS should never be reached when ElevenLabs succeeds")

    def run():
        monkeypatch.setattr(hf_client, "_call_elevenlabs", fake_elevenlabs_call)
        monkeypatch.setattr(hf_client._http, "post", unexpected_post)
        audio = asyncio.run(
            hf_client.text_to_speech("Hola desde ElevenLabs", "es", persona_id="core-elena")
        )
        assert audio == b"FAKE_ELEVENLABS_AUDIO"

    _with_cache_dir(tmp_path, lambda: _with_elevenlabs_configured({"core-elena": "voice-elena-123"}, run))


def test_text_to_speech_falls_through_to_parler_when_elevenlabs_fails(monkeypatch, tmp_path):
    async def failing_elevenlabs_call(text, voice_id):
        return None

    def fake_space_call(text, description):
        return b"FAKE_SPACE_AUDIO_AFTER_ELEVENLABS_FAILURE"

    async def failing_post(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def run():
        monkeypatch.setattr(hf_client, "_call_elevenlabs", failing_elevenlabs_call)
        monkeypatch.setattr(hf_client._http, "post", failing_post)
        monkeypatch.setattr(hf_client_module, "_call_parler_space", fake_space_call)
        audio = asyncio.run(
            hf_client.text_to_speech(
                "Texto de respaldo",
                "es",
                voice_description="a distinctive test voice",
                persona_id="core-elena",
            )
        )
        assert audio == b"FAKE_SPACE_AUDIO_AFTER_ELEVENLABS_FAILURE"

    def run_with_hf():
        _with_hf_configured(run)

    _with_cache_dir(tmp_path, lambda: _with_elevenlabs_configured({"core-elena": "voice-elena-123"}, run_with_hf))


def test_text_to_speech_skips_elevenlabs_when_persona_has_no_mapped_voice(monkeypatch, tmp_path):
    async def unexpected_elevenlabs_call(text, voice_id):
        raise AssertionError("ElevenLabs should never be called without a mapped voice_id")

    async def failing_post(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def failing_space_call(text, description):
        return None

    def run():
        monkeypatch.setattr(hf_client, "_call_elevenlabs", unexpected_elevenlabs_call)
        monkeypatch.setattr(hf_client._http, "post", failing_post)
        monkeypatch.setattr(hf_client_module, "_call_parler_space", failing_space_call)
        audio = asyncio.run(
            hf_client.text_to_speech("Sin voz asignada", "es", persona_id="core-marcus")
        )
        assert audio is None

    def run_with_hf():
        _with_hf_configured(run)

    # core-marcus is deliberately absent from the voice map.
    _with_cache_dir(tmp_path, lambda: _with_elevenlabs_configured({"core-elena": "voice-elena-123"}, run_with_hf))
