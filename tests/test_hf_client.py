"""Unit tests for _HFGuard, the Hugging Face rate/budget guard in
hf_client.py (see its docstring for why it exists: HF is the one AI tier
in this app with a real credit-limited budget, and the only one used as a
last-resort fallback across four different call sites — chat, STT, TTS,
video). Tests the guard's pure state machine directly, without touching
the network, so they stay fast and deterministic."""

from backend.hf_client import _HFGuard


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
