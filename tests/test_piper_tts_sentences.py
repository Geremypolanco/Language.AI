"""Tests for backend/piper_tts.split_into_sentences — pure text logic, no
network, no ONNX runtime involved."""

from backend.piper_tts import split_into_sentences


def test_split_into_sentences_splits_on_terminal_punctuation():
    result = split_into_sentences("Hello there. How are you? I'm fine!")
    assert result == ["Hello there.", "How are you?", "I'm fine!"]


def test_split_into_sentences_single_sentence_no_terminal_punctuation():
    assert split_into_sentences("just one clause with no period") == ["just one clause with no period"]


def test_split_into_sentences_empty_input():
    assert split_into_sentences("") == []
    assert split_into_sentences("   ") == []


def test_split_into_sentences_collapses_extra_whitespace_between_sentences():
    result = split_into_sentences("First.    Second.\n\nThird.")
    assert result == ["First.", "Second.", "Third."]
