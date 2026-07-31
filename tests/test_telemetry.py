"""Tests for backend/telemetry.py — pure timing/formatting logic."""

import json
import logging
import time

from backend import telemetry


def test_timed_measures_elapsed_time_in_milliseconds():
    box: dict = {}
    with telemetry.timed(box):
        time.sleep(0.02)
    assert box["elapsed_ms"] >= 15  # generous floor to avoid flakiness


def test_log_tutor_turn_emits_valid_json_with_expected_fields(caplog):
    with caplog.at_level(logging.INFO, logger="lingua.telemetry"):
        telemetry.log_tutor_turn(
            user_id="u1", chat_ms=120.5, tts_ms=340.2, chars_in=10, chars_out=42, sentence_count=3
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "tutor_turn"
    assert payload["user_id"] == "u1"
    assert payload["chat_ms"] == 120.5
    assert payload["tts_ms"] == 340.2
    assert payload["total_ms"] == 460.7
    assert payload["chars_in"] == 10
    assert payload["chars_out"] == 42
    assert payload["sentence_count"] == 3
