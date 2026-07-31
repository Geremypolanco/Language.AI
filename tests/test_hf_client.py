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
