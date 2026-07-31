import json
import time

from backend import telemetry


def test_measure_ms_reports_a_realistic_positive_duration():
    with telemetry.measure_ms() as timer:
        time.sleep(0.01)
    assert timer["duration_ms"] >= 10.0
    assert timer["duration_ms"] < 1000.0


def test_measure_ms_still_records_duration_when_the_block_raises():
    timer_ref = {}
    try:
        with telemetry.measure_ms() as timer:
            timer_ref["timer"] = timer
            raise ValueError("boom")
    except ValueError:
        pass
    assert "duration_ms" in timer_ref["timer"]


def test_log_student_turn_emits_one_structured_json_line(caplog):
    with caplog.at_level("INFO", logger="lingua.telemetry"):
        telemetry.log_student_turn(
            duration_ms=123.45,
            voice_tier_utilized="elevenlabs",
            tokens_consumed=57,
            circuit_breaker_state=False,
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload == {
        "event": "student_turn",
        "duration_ms": 123.45,
        "voice_tier_utilized": "elevenlabs",
        "tokens_consumed": 57,
        "circuit_breaker_state": False,
    }


def test_log_student_turn_reports_none_tokens_honestly_when_unavailable(caplog):
    with caplog.at_level("INFO", logger="lingua.telemetry"):
        telemetry.log_student_turn(
            duration_ms=10.0,
            voice_tier_utilized="none",
            tokens_consumed=None,
            circuit_breaker_state=True,
        )

    payload = json.loads(caplog.records[0].message)
    assert payload["tokens_consumed"] is None
    assert payload["circuit_breaker_state"] is True
