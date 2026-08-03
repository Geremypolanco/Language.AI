from backend.curriculum import (
    ALPHABET_TOPIC,
    LessonRequest,
    all_units,
    build_conversation_system_prompt,
    build_exercise_generation_prompt,
    build_review_exercise_prompt,
    exercise_mix_for,
    get_unit,
    resolve_exercise_mix,
    units_for_level,
)
from backend.models import CEFRLevel, ExerciseType


def test_cefr_level_progression():
    assert CEFRLevel.A1.next == CEFRLevel.A2
    assert CEFRLevel.C2.next == CEFRLevel.NATIVE
    assert CEFRLevel.NATIVE.next == CEFRLevel.NATIVE  # caps out
    assert CEFRLevel.A1.uses_translation is False
    assert CEFRLevel.A2.uses_translation is True


def test_a1_uses_immersion_exercise_mix():
    mix = exercise_mix_for(CEFRLevel.A1)
    assert ExerciseType.IMAGE_MATCH in mix
    assert ExerciseType.FREE_CONVERSATION_PROMPT not in mix


def test_b1_unlocks_free_conversation():
    mix = exercise_mix_for(CEFRLevel.B1)
    assert ExerciseType.FREE_CONVERSATION_PROMPT in mix


def test_units_are_ordered_and_unique_ids():
    units = units_for_level(CEFRLevel.A1)
    assert len(units) > 0
    ids = [u.id for u in units]
    assert len(ids) == len(set(ids))
    assert [u.order for u in units] == sorted(u.order for u in units)


def test_get_unit_roundtrips_through_all_units():
    any_unit = all_units()[0]
    assert get_unit(any_unit.id).id == any_unit.id
    assert get_unit("does-not-exist") is None


def test_exercise_prompt_hides_translation_for_a1():
    unit = units_for_level(CEFRLevel.A1)[0]
    req = LessonRequest(unit=unit, native_lang="English", target_lang="Spanish", interests=[], recent_mistakes=[])
    prompt = build_exercise_generation_prompt(req)
    assert "Do NOT include any native-language translation" in prompt


def test_exercise_prompt_includes_translation_for_a2():
    unit = units_for_level(CEFRLevel.A2)[0]
    req = LessonRequest(unit=unit, native_lang="English", target_lang="Spanish", interests=[], recent_mistakes=[])
    prompt = build_exercise_generation_prompt(req)
    assert "Include the native-language translation" in prompt


def test_exercise_prompt_weaves_in_mistakes_and_interests():
    unit = units_for_level(CEFRLevel.A2)[0]
    req = LessonRequest(
        unit=unit,
        native_lang="English",
        target_lang="Spanish",
        interests=["football"],
        recent_mistakes=["greetings.hello"],
    )
    prompt = build_exercise_generation_prompt(req)
    assert "football" in prompt
    assert "greetings.hello" in prompt


def test_exercise_prompt_scales_difficulty_with_cefr_level():
    beginner_unit = units_for_level(CEFRLevel.A2)[0]
    advanced_unit = units_for_level(CEFRLevel.C2)[0]
    beginner_prompt = build_exercise_generation_prompt(
        LessonRequest(unit=beginner_unit, native_lang="English", target_lang="Spanish", interests=[], recent_mistakes=[])
    )
    advanced_prompt = build_exercise_generation_prompt(
        LessonRequest(unit=advanced_unit, native_lang="English", target_lang="Spanish", interests=[], recent_mistakes=[])
    )
    assert "Difficulty: beginner" in beginner_prompt
    assert "Difficulty: advanced" in advanced_prompt
    assert "7-year-old" in beginner_prompt and "7-year-old" in advanced_prompt


def test_exercise_prompt_requires_communicative_real_world_context():
    unit = units_for_level(CEFRLevel.A2)[0]
    req = LessonRequest(unit=unit, native_lang="English", target_lang="Spanish", interests=[], recent_mistakes=[])
    prompt = build_exercise_generation_prompt(req)
    assert "COMMUNICATIVE APPROACH" in prompt
    assert "isolated dictionary word" in prompt


def test_review_prompt_asks_for_recombination_not_bare_repetition():
    items = [
        {"vocab_key": "greetings.hello", "target_text": "hola", "native_text": "hello", "unit_id": "A1-0"},
        {"vocab_key": "food.bread", "target_text": "pan", "native_text": "bread", "unit_id": "A1-2"},
    ]
    prompt = build_review_exercise_prompt(items, native_lang="English", target_lang="Spanish")
    assert "hola" in prompt
    assert "pan" in prompt
    assert "fresh, natural" in prompt
    assert "exactly 2 objects" in prompt


def test_a1_and_b1_have_explicit_grammar_throughline_units():
    # A genuine 0-to-native curriculum needs deliberate grammar progression,
    # not just vocabulary-by-topic — verbs (to be/to have) and tenses
    # (past at A2, future at B1) are taught as their own units.
    a1_topics = [u.topic for u in units_for_level(CEFRLevel.A1)]
    b1_topics = [u.topic for u in units_for_level(CEFRLevel.B1)]
    assert "Basic sentence structure: to be & to have" in a1_topics
    assert "Future tense & making predictions" in b1_topics


def test_alphabet_unit_is_first_a1_unit_and_excludes_image_match():
    alphabet_unit = units_for_level(CEFRLevel.A1)[0]
    assert alphabet_unit.topic == ALPHABET_TOPIC
    mix = resolve_exercise_mix(alphabet_unit)
    assert ExerciseType.IMAGE_MATCH not in mix


def test_mix_override_always_wins_even_for_the_alphabet_unit():
    # Free-practice mode (lessons.py's get_practice_exercises) always passes
    # an explicit mix_override for whatever modality the learner picked —
    # that choice must never be silently replaced by a topic-specific
    # default, alphabet included.
    alphabet_unit = units_for_level(CEFRLevel.A1)[0]
    override = [ExerciseType.IMAGE_MATCH] * 3
    assert resolve_exercise_mix(alphabet_unit, override) == override


def test_alphabet_teaching_note_only_applies_to_the_alphabet_units_own_mix():
    # Regression: build_exercise_generation_prompt used to force "teach one
    # letter at a time" instructions onto ANY request against the alphabet
    # unit, including free-practice requests that pass their own
    # mix_override for an unrelated modality (e.g. free conversation) — see
    # lessons.py's get_practice_exercises, which now avoids seeding practice
    # content from the alphabet unit at all, but the prompt builder itself
    # should also never leak the note when a caller explicitly overrides the
    # mix for something the alphabet note doesn't apply to.
    alphabet_unit = units_for_level(CEFRLevel.A1)[0]
    req = LessonRequest(unit=alphabet_unit, native_lang="English", target_lang="Korean", interests=[], recent_mistakes=[])

    real_lesson_prompt = build_exercise_generation_prompt(req)
    assert "ONE letter" in real_lesson_prompt

    practice_prompt = build_exercise_generation_prompt(req, mix_override=[ExerciseType.FREE_CONVERSATION_PROMPT] * 5)
    assert "ONE letter" not in practice_prompt


def test_alphabet_unit_never_asks_for_bare_letter_as_audio_text():
    # Regression: the prompt used to let the model choose between a bare
    # letter/character or a real word for audio_text ("...or a single word
    # that starts with it if letters alone can't be pronounced
    # meaningfully") — confirmed live that a bare isolated Korean jamo
    # (ㅏ) sent to text-to-speech made synthesis fail outright ("Audio no
    # disponible"), since a real speech engine is trained on natural
    # speech, not isolated letter-names. audio_text must now always be a
    # real, pronounceable word — never left to the model's discretion.
    alphabet_unit = units_for_level(CEFRLevel.A1)[0]
    req = LessonRequest(unit=alphabet_unit, native_lang="Spanish", target_lang="Korean", interests=[], recent_mistakes=[])
    prompt = build_exercise_generation_prompt(req)
    assert "NEVER use the bare letter/character alone" in prompt
    assert "letters alone can't be pronounced meaningfully" not in prompt


def test_conversation_prompt_adapts_to_level():
    beginner = build_conversation_system_prompt("Spanish", "English", CEFRLevel.A1, [])
    advanced = build_conversation_system_prompt("Spanish", "English", CEFRLevel.C2, [])
    assert "very simple" in beginner
    assert "native pace" in advanced
