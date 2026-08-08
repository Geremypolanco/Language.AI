"""Unit tests for the chat-provider cascade extracted into
backend/ai_providers/ (see hf_client.py's chat() and its module
docstring for the orchestration this backs). Providers are tested here
against fake httpx.Response objects, no real network. HFClient.chat()'s
own orchestration (try providers in order, return the first success, raise
if all fail) is tested separately against fake AIProvider stubs, not
these real providers — two independent seams, tested independently.

No pytest-asyncio in this project (see every other async test in this
suite) — async calls run via asyncio.run() inside a plain `def test_x()`,
same convention as tests/test_hf_client.py."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.ai_providers import base as ai_base
from backend.ai_providers.base import post_with_retry
from backend.ai_providers.groq import GroqProvider
from backend.ai_providers.huggingface import HFProvider
from backend.ai_providers.pollinations import PollinationsProvider
from backend.config import settings

_MESSAGES = [{"role": "user", "content": "hola"}]


def _fake_response(status_code: int, body: dict | None = None, text: str = "") -> httpx.Response:
    if body is not None:
        return httpx.Response(status_code, json=body)
    return httpx.Response(status_code, text=text)


@pytest.fixture
def settings_field():
    """Settings is a frozen dataclass — object.__setattr__ is the same
    pattern already used elsewhere in this app (test_audio.py,
    test_hf_client.py) to override a frozen field for a test."""
    originals: dict[str, object] = {}

    def _set(name: str, value) -> None:
        if name not in originals:
            originals[name] = getattr(settings, name)
        object.__setattr__(settings, name, value)

    yield _set
    for name, value in originals.items():
        object.__setattr__(settings, name, value)


# ── post_with_retry ───────────────────────────────────────────────────────


class _FakeHttpClient:
    """Stands in for httpx.AsyncClient — records calls and, if configured,
    raises httpx.TransportError on the first N of them before succeeding,
    so post_with_retry's actual retry-once behavior gets exercised without
    a real network."""

    def __init__(self, transport_failures: int = 0) -> None:
        self.calls = 0
        self._transport_failures = transport_failures

    async def post(self, url, **kwargs):
        self.calls += 1
        if self.calls <= self._transport_failures:
            raise httpx.TransportError("simulated network blip")
        return _fake_response(200, {"ok": True})


def test_post_with_retry_succeeds_on_first_attempt():
    client = _FakeHttpClient(transport_failures=0)
    resp = asyncio.run(post_with_retry(client, "http://example.test"))
    assert resp.status_code == 200
    assert client.calls == 1


async def _no_sleep(_seconds: float) -> None:
    return None


def test_post_with_retry_retries_once_after_transport_error(monkeypatch):
    # Avoids the real 0.5s backoff between attempts — same "don't actually
    # sleep in a test" discipline as HFGuard's cooldown_s=-1.0 trick above.
    # (asyncio.sleep is the same module-level object everywhere it's
    # imported, so patching it here must not call the real thing recursively.)
    monkeypatch.setattr(ai_base.asyncio, "sleep", _no_sleep)
    client = _FakeHttpClient(transport_failures=1)
    resp = asyncio.run(post_with_retry(client, "http://example.test"))
    assert resp.status_code == 200
    assert client.calls == 2  # first attempt failed, second succeeded


def test_post_with_retry_raises_after_exhausting_the_one_retry(monkeypatch):
    monkeypatch.setattr(ai_base.asyncio, "sleep", _no_sleep)
    client = _FakeHttpClient(transport_failures=2)
    with pytest.raises(httpx.TransportError):
        asyncio.run(post_with_retry(client, "http://example.test"))
    assert client.calls == 2  # never tries a third time


# ── GroqProvider ─────────────────────────────────────────────────────────


def test_groq_not_configured_without_api_key(settings_field):
    settings_field("groq_api_key", "")
    assert GroqProvider(http=object()).configured is False


def test_groq_configured_with_api_key(settings_field):
    settings_field("groq_api_key", "test-key")
    assert GroqProvider(http=object()).configured is True


def test_groq_chat_skips_without_api_key(settings_field):
    settings_field("groq_api_key", "")
    provider = GroqProvider(http=object())
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_groq_chat_returns_content_on_success(monkeypatch, settings_field):
    settings_field("groq_api_key", "test-key")
    provider = GroqProvider(http=object())

    async def fake_post(client, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        return _fake_response(200, {"choices": [{"message": {"content": "hola!"}}]})

    monkeypatch.setattr("backend.ai_providers.groq.post_with_retry", fake_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) == "hola!"


def test_groq_chat_returns_none_on_non_200(monkeypatch, settings_field):
    settings_field("groq_api_key", "test-key")
    provider = GroqProvider(http=object())

    async def fake_post(client, url, **kwargs):
        return _fake_response(500, text="server error")

    monkeypatch.setattr("backend.ai_providers.groq.post_with_retry", fake_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_groq_chat_returns_none_on_exception(monkeypatch, settings_field):
    settings_field("groq_api_key", "test-key")
    provider = GroqProvider(http=object())

    async def failing_post(client, url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.ai_providers.groq.post_with_retry", failing_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


# ── PollinationsProvider ─────────────────────────────────────────────────


def test_pollinations_always_configured():
    # No required key, unlike Groq/HF — see PollinationsProvider's docstring.
    assert PollinationsProvider(http=object()).configured is True


def test_pollinations_chat_returns_content_on_success(monkeypatch):
    provider = PollinationsProvider(http=object())

    async def fake_post(client, url, **kwargs):
        return _fake_response(200, {"choices": [{"message": {"content": "hi!"}}]})

    monkeypatch.setattr("backend.ai_providers.pollinations.post_with_retry", fake_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) == "hi!"


def test_pollinations_chat_returns_none_on_non_200(monkeypatch):
    provider = PollinationsProvider(http=object())

    async def fake_post(client, url, **kwargs):
        return _fake_response(402, text="budget too low")

    monkeypatch.setattr("backend.ai_providers.pollinations.post_with_retry", fake_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_pollinations_chat_returns_none_on_failure(monkeypatch):
    provider = PollinationsProvider(http=object())

    async def failing_post(client, url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.ai_providers.pollinations.post_with_retry", failing_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_pollinations_headers_empty_without_token(settings_field):
    settings_field("pollinations_token", "")
    assert PollinationsProvider(http=object())._headers() == {}


def test_pollinations_headers_include_token_when_set(settings_field):
    settings_field("pollinations_token", "tok123")
    assert PollinationsProvider(http=object())._headers() == {"Authorization": "Bearer tok123"}


# ── HFProvider ───────────────────────────────────────────────────────────


def test_hf_not_configured_without_token(settings_field):
    settings_field("hf_token", "")
    provider = HFProvider(http=object(), hf_guard=ai_base.HFGuard(daily_budget=1000))
    assert provider.configured is False


def test_hf_chat_skips_when_not_configured(settings_field):
    settings_field("hf_token", "")
    provider = HFProvider(http=object(), hf_guard=ai_base.HFGuard(daily_budget=1000))
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_hf_chat_skips_when_guard_denies(settings_field):
    settings_field("hf_token", "test-token")
    guard = ai_base.HFGuard(daily_budget=1000)
    guard.record_rate_limited()  # opens the circuit breaker
    provider = HFProvider(http=object(), hf_guard=guard)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


def test_hf_chat_returns_content_and_records_usage_on_success(monkeypatch, settings_field):
    settings_field("hf_token", "test-token")
    guard = ai_base.HFGuard(daily_budget=1000)
    provider = HFProvider(http=object(), hf_guard=guard)

    async def fake_post(client, url, **kwargs):
        return _fake_response(200, {"choices": [{"message": {"content": "hola!"}}]})

    monkeypatch.setattr("backend.ai_providers.huggingface.post_with_retry", fake_post)
    result = asyncio.run(provider.chat(_MESSAGES, 100, 0.5))
    assert result == "hola!"
    assert guard._used_today > 0  # usage was actually recorded on the shared guard


def test_hf_chat_opens_circuit_on_rate_limit(monkeypatch, settings_field):
    settings_field("hf_token", "test-token")
    guard = ai_base.HFGuard(daily_budget=1000)
    provider = HFProvider(http=object(), hf_guard=guard)

    async def fake_post(client, url, **kwargs):
        return _fake_response(429, text="rate limited")

    monkeypatch.setattr("backend.ai_providers.huggingface.post_with_retry", fake_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None
    assert guard.allowed() is False


def test_hf_chat_returns_none_on_exception(monkeypatch, settings_field):
    settings_field("hf_token", "test-token")
    guard = ai_base.HFGuard(daily_budget=1000)
    provider = HFProvider(http=object(), hf_guard=guard)

    async def failing_post(client, url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.ai_providers.huggingface.post_with_retry", failing_post)
    assert asyncio.run(provider.chat(_MESSAGES, 100, 0.5)) is None


# ── HFClient.chat() orchestration (fake providers, not the real three) ───


class _StubProvider:
    def __init__(self, result: str | None) -> None:
        self._result = result

    async def chat(self, messages, max_tokens, temperature):
        return self._result


def test_hfclient_chat_disabled_in_test_environment():
    # settings.testing is True for this whole suite (see conftest.py) —
    # confirms the refactor kept this guard as chat()'s very first check,
    # ahead of ever touching a provider.
    from backend.hf_client import HFClientError, hf_client

    with pytest.raises(HFClientError):
        asyncio.run(hf_client.chat(_MESSAGES))


def test_hfclient_chat_returns_first_successful_provider(monkeypatch, settings_field):
    from backend.hf_client import hf_client

    settings_field("testing", False)
    monkeypatch.setattr(
        hf_client, "_chat_providers", [_StubProvider(None), _StubProvider("second wins"), _StubProvider("unreached")]
    )
    assert asyncio.run(hf_client.chat(_MESSAGES)) == "second wins"


def test_hfclient_chat_raises_when_every_provider_fails(monkeypatch, settings_field):
    from backend.hf_client import HFClientError, hf_client

    settings_field("testing", False)
    monkeypatch.setattr(hf_client, "_chat_providers", [_StubProvider(None), _StubProvider(None)])
    with pytest.raises(HFClientError):
        asyncio.run(hf_client.chat(_MESSAGES))
