"""Curriculum: the language-agnostic skill tree (Duolingo-style path) plus the
prompt templates used to have the HF model generate the actual target-language
content for a given topic, level, and user (Rosetta-Stone-style immersion at
the early levels, free conversation practice from B1 onward).

The topic list itself is language-agnostic — the LLM produces the target-language
vocabulary/sentences/questions at request time, tailored to the learner's native
language, interests, and past mistakes. This is what lets one curriculum serve
any language pair instead of hand-authoring word lists per language.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CEFRLevel, ExerciseType, Unit

# (topic, description_native placeholder key) per level, in learning order.
_TOPICS_BY_LEVEL: dict[CEFRLevel, list[str]] = {
    CEFRLevel.A1: [
        # Always first: before any vocabulary, a learner needs to be able to
        # read the target language at all — its alphabet/writing system,
        # individual letters or characters, and their sounds. Skipping
        # straight to "Greetings" assumes a shared (or at least readable)
        # script, which silently fails for anyone learning a language whose
        # writing system they've never seen (see build_exercise_generation_
        # prompt's ALPHABET_TOPIC handling below).
        "Alphabet & first sounds",
        "Greetings & introductions",
        "Numbers & counting",
        "Family",
        "Food & drink",
        "Colors & shapes",
        "Everyday objects",
        "Days & time",
    ],
    CEFRLevel.A2: [
        "Daily routines",
        "Shopping",
        "Directions & places in town",
        "Weather",
        "Hobbies",
        "Past tense: simple stories",
        "Making plans",
    ],
    CEFRLevel.B1: [
        "Travel & transportation",
        "Health & the body",
        "Work & school",
        "Opinions & preferences",
        "Describing people",
        "Telling a past experience",
        "Free conversation: small talk",
    ],
    CEFRLevel.B2: [
        "News & current events",
        "Emotions & relationships",
        "Giving advice",
        "Hypotheticals",
        "Debating opinions",
        "Free conversation: everyday problems",
    ],
    CEFRLevel.C1: [
        "Idioms & colloquialisms",
        "Nuanced arguments",
        "Professional communication",
        "Humor & wordplay",
        "Free conversation: abstract topics",
    ],
    CEFRLevel.C2: [
        "Regional accents & slang",
        "Literary & rhetorical language",
        "Rapid native-speed conversation",
        "Free conversation: any topic, native pace",
    ],
    CEFRLevel.NATIVE: [
        "Open conversation practice",
    ],
}

# Spanish label for each topic key above — used only for the no-HF_TOKEN
# template fallback's placeholder text (backend/hf_client.py's
# _fallback_exercises); the frontend's skill path/recent-lessons UI has its
# own copy of this map (frontend/app.js TOPIC_ES) since there's no shared
# JS/Python module in this repo.
_TOPIC_ES: dict[str, str] = {
    "Alphabet & first sounds": "El alfabeto y los primeros sonidos",
    "Greetings & introductions": "Saludos y presentaciones",
    "Numbers & counting": "Números y conteo",
    "Family": "Familia",
    "Food & drink": "Comida y bebida",
    "Colors & shapes": "Colores y formas",
    "Everyday objects": "Objetos cotidianos",
    "Days & time": "Días y horas",
    "Daily routines": "Rutinas diarias",
    "Shopping": "De compras",
    "Directions & places in town": "Direcciones y lugares en la ciudad",
    "Weather": "El clima",
    "Hobbies": "Pasatiempos",
    "Past tense: simple stories": "Pasado: historias sencillas",
    "Making plans": "Hacer planes",
    "Travel & transportation": "Viajes y transporte",
    "Health & the body": "Salud y el cuerpo",
    "Work & school": "Trabajo y escuela",
    "Opinions & preferences": "Opiniones y preferencias",
    "Describing people": "Describir personas",
    "Telling a past experience": "Contar una experiencia pasada",
    "Free conversation: small talk": "Conversación libre: charla informal",
    "News & current events": "Noticias y actualidad",
    "Emotions & relationships": "Emociones y relaciones",
    "Giving advice": "Dar consejos",
    "Hypotheticals": "Hipótesis",
    "Debating opinions": "Debatir opiniones",
    "Free conversation: everyday problems": "Conversación libre: problemas cotidianos",
    "Idioms & colloquialisms": "Modismos y coloquialismos",
    "Nuanced arguments": "Argumentos matizados",
    "Professional communication": "Comunicación profesional",
    "Humor & wordplay": "Humor y juegos de palabras",
    "Free conversation: abstract topics": "Conversación libre: temas abstractos",
    "Regional accents & slang": "Acentos regionales y jerga",
    "Literary & rhetorical language": "Lenguaje literario y retórico",
    "Rapid native-speed conversation": "Conversación a velocidad nativa",
    "Free conversation: any topic, native pace": "Conversación libre: cualquier tema, ritmo nativo",
    "Open conversation practice": "Práctica de conversación abierta",
}


def topic_es(topic: str) -> str:
    return _TOPIC_ES.get(topic, topic)


# Exercise mix per level — early levels lean on image/audio immersion
# (Rosetta Stone), later levels lean on translation, production, and free
# conversation (Duolingo's later skill tree + real dialogue practice).
_EXERCISE_MIX: dict[CEFRLevel, list[ExerciseType]] = {
    CEFRLevel.A1: [
        ExerciseType.IMAGE_MATCH,
        ExerciseType.IMAGE_MATCH,
        ExerciseType.LISTEN_TYPE,
        ExerciseType.MULTIPLE_CHOICE,
        ExerciseType.SPEAK_REPEAT,
    ],
    CEFRLevel.A2: [
        ExerciseType.IMAGE_MATCH,
        ExerciseType.TRANSLATE_TO_TARGET,
        ExerciseType.TRANSLATE_TO_NATIVE,
        ExerciseType.FILL_BLANK,
        ExerciseType.SPEAK_REPEAT,
        # A taste of free-form conversation this early (rather than waiting
        # until B1) keeps lessons feeling like a real exchange, not just a
        # quiz — kept short/scaffolded since the learner is still early.
        ExerciseType.FREE_CONVERSATION_PROMPT,
    ],
    CEFRLevel.B1: [
        ExerciseType.TRANSLATE_TO_TARGET,
        ExerciseType.FILL_BLANK,
        ExerciseType.MULTIPLE_CHOICE,
        ExerciseType.SPEAK_REPEAT,
        ExerciseType.FREE_CONVERSATION_PROMPT,
    ],
    CEFRLevel.B2: [
        ExerciseType.TRANSLATE_TO_TARGET,
        ExerciseType.FILL_BLANK,
        ExerciseType.FREE_CONVERSATION_PROMPT,
        ExerciseType.FREE_CONVERSATION_PROMPT,
    ],
    CEFRLevel.C1: [
        ExerciseType.FILL_BLANK,
        ExerciseType.FREE_CONVERSATION_PROMPT,
        ExerciseType.FREE_CONVERSATION_PROMPT,
    ],
    CEFRLevel.C2: [
        ExerciseType.FREE_CONVERSATION_PROMPT,
        ExerciseType.FREE_CONVERSATION_PROMPT,
    ],
    CEFRLevel.NATIVE: [ExerciseType.FREE_CONVERSATION_PROMPT],
}


def units_for_level(level: CEFRLevel) -> list[Unit]:
    topics = _TOPICS_BY_LEVEL.get(level, [])
    return [
        Unit(
            id=f"{level.value}-{i}",
            topic=topic,
            level=level,
            order=i,
            title_native=topic,
            description_native=f"{level.value} unit: {topic}",
        )
        for i, topic in enumerate(topics)
    ]


def all_units() -> list[Unit]:
    units: list[Unit] = []
    for level in CEFRLevel:
        units.extend(units_for_level(level))
    return units


def get_unit(unit_id: str) -> Unit | None:
    for unit in all_units():
        if unit.id == unit_id:
            return unit
    return None


ALPHABET_TOPIC = "Alphabet & first sounds"

# Bumped whenever build_exercise_generation_prompt's alphabet-specific
# instructions change in a way that fixes previously-generated content —
# hf_client.generate_exercises folds this into its disk cache key (only for
# the alphabet unit) so a fix here actually reaches learners who already
# have a cached, now-known-bad exercise set, instead of that unit silently
# keeping its stale content forever (disk caches never expire on their own).
# History: v2 stopped audio_text ever being a bare, isolated letter/character
# — confirmed live that sending a lone Korean jamo (ㅏ) to text-to-speech
# made synthesis fail outright ("Audio no disponible"), since real speech
# engines are trained on natural speech, not isolated letter-names.
ALPHABET_PROMPT_VERSION = "v2"

# Bumped whenever generate_exercises' output SHAPE changes in a way that
# affects every unit, not just the alphabet one — unlike
# ALPHABET_PROMPT_VERSION, hf_client folds this into every unit's cache key
# unconditionally. History: v2 added a self-paced "vocab_intro" teaching
# card before each graded exercise (see hf_client._with_teaching_intros) —
# previously every lesson jumped straight to quizzing the learner on a word
# they'd never actually been shown, which is backwards for anyone actually
# trying to learn the word for the first time. v3 rewrote the prompt to
# require real communicative context (a situational phrase + a scene-
# depicting image_prompt) instead of isolated dictionary words — without
# this bump, learners who'd already generated a unit kept seeing the old
# flashcard-style content forever, since the prompt fix never reached them.
EXERCISE_FORMAT_VERSION = "v3"

# image_match doesn't make sense for a single letter/character — there's no
# real "picture of a sound" to match against, and asking the model to
# invent one anyway produces incoherent exercises (or, worse, the model
# just ignores the letter-teaching instructions and generates ordinary
# vocabulary instead). Recognizing/sounding out a letter is a
# listening/multiple-choice/pronunciation task, not a visual one.
_ALPHABET_MIX: list[ExerciseType] = [
    ExerciseType.MULTIPLE_CHOICE,
    ExerciseType.LISTEN_TYPE,
    ExerciseType.MULTIPLE_CHOICE,
    ExerciseType.SPEAK_REPEAT,
    ExerciseType.LISTEN_TYPE,
]


def exercise_mix_for(level: CEFRLevel) -> list[ExerciseType]:
    return _EXERCISE_MIX.get(level, [ExerciseType.FREE_CONVERSATION_PROMPT])


def resolve_exercise_mix(unit: Unit, mix_override: list[ExerciseType] | None = None) -> list[ExerciseType]:
    """The single source of truth for "which exercise types for this unit" —
    every caller (real generation, the offline fallback generator, the
    prompt builder) must go through this so a topic-specific override like
    the alphabet unit's can't silently drift out of sync between them."""
    if mix_override is not None:
        return mix_override
    if unit.topic == ALPHABET_TOPIC:
        return _ALPHABET_MIX
    return exercise_mix_for(unit.level)


@dataclass
class LessonRequest:
    unit: Unit
    native_lang: str
    target_lang: str
    interests: list[str]
    recent_mistakes: list[str]  # target-language words/phrases the user got wrong recently


# Target languages whose everyday writing system a Latin-script reader
# cannot sound out at all without being taught it first — "pure immersion,
# no translation" (the A1 default below) silently fails for these, since an
# image can teach what a word *means* but not how to *read* unfamiliar
# characters. Scoped to what onboarding's language picker actually offers
# (see frontend/client/src/lib/languages.ts) rather than every script on
# earth.
_NON_LATIN_SCRIPT_LANGS = {"ja", "ko", "zh", "ru"}


def _uses_unfamiliar_script(target_lang: str) -> bool:
    return target_lang.lower()[:2] in _NON_LATIN_SCRIPT_LANGS


def _difficulty_note_for_level(level: CEFRLevel) -> str:
    """Explicit vocabulary/grammar guidance per CEFR band. Naming just the
    bare CEFR code (e.g. "at CEFR level B1") leans entirely on the model
    already knowing that standard precisely — fine for a strong model, but
    the chat() call generating this content can fall all the way through to
    Qwen2.5-7B-Instruct on Hugging Face (see hf_client.py) when Groq and
    Pollinations are both unavailable, and a smaller model calibrates
    difficulty more reliably when it's spelled out than when it has to
    infer it from a label alone. Mirrors the same rank-based tiering
    build_conversation_system_prompt already uses for spoken replies,
    applied here to written exercise content instead."""
    rank = level.rank
    if rank <= 1:  # A1, A2
        return (
            "Difficulty: beginner. Use only common, everyday, high-frequency words — nothing "
            "obscure or technical. Short sentences. Present tense only, unless the topic itself "
            "is about a different tense. No idioms, no compound/nested clauses."
        )
    if rank <= 3:  # B1, B2
        return (
            "Difficulty: intermediate. Use everyday vocabulary a comfortable-but-not-native "
            "speaker would know. Natural sentence length, past and future tenses are fine, a "
            "few common idioms are okay if explained."
        )
    # C1, C2, NATIVE
    return (
        "Difficulty: advanced. Use natural, native-level vocabulary, idioms, and nuanced "
        "grammar — the same complexity a native speaker would use in everyday life."
    )


def build_exercise_generation_prompt(req: LessonRequest, mix_override: list[ExerciseType] | None = None) -> str:
    """Builds the instruction sent to the HF chat model to produce a JSON batch
    of exercises for this unit, personalized to the learner. `mix_override` lets
    a caller force a single exercise type repeated (used by the free-practice
    mode, where the learner picks the skill — reading/listening/speaking/images/
    conversation — instead of following the level's default mix)."""
    mix = resolve_exercise_mix(req.unit, mix_override)
    types_list = ", ".join(t.value for t in mix)
    interests = ", ".join(req.interests) if req.interests else "everyday life"
    mistakes = (
        f"The learner recently struggled with: {', '.join(req.recent_mistakes)}. "
        "Weave 1-2 of these back in for extra practice."
        if req.recent_mistakes
        else ""
    )

    unfamiliar_script = _uses_unfamiliar_script(req.target_lang)
    # "Pure immersion, no translation" assumes the learner can at least read
    # the target text — true for A1 Spanish/French/etc, false the instant
    # the target language uses a script the learner has never seen. Force
    # translation on in that case regardless of CEFR level; a real
    # transliteration (see below) still keeps the immersion goal for
    # everything except literacy itself.
    if unfamiliar_script:
        show_translation = (
            f"ALWAYS include the native-language translation in native_text — {req.target_lang} does not "
            f"share {req.native_lang}'s writing system, so an image alone cannot teach a learner what an "
            "unfamiliar word means. In native_text, put BOTH the translation and a romanized "
            'transliteration of target_text, like this: "hello — annyeonghaseyo". Never leave a learner '
            "looking at a script they cannot read with no way to know what it says or means."
        )
    elif req.unit.level.uses_translation:
        show_translation = "Include the native-language translation in native_text."
    else:
        show_translation = (
            "Do NOT include any native-language translation — this level is pure immersion: "
            "teach meaning only through the image_prompt and example sentence context."
        )

    alphabet_unit_note = ""
    # Gated on mix_override being unset: the alphabet unit's own fixed lesson
    # (mix_override=None, resolve_exercise_mix falls through to _ALPHABET_MIX)
    # should teach individual letters, but free-practice mode (lessons.py's
    # get_practice_exercises) always passes an explicit mix_override for
    # whatever modality the learner picked — conversation, translation,
    # listening — and forcing "each exercise is one single letter" onto e.g.
    # a free-conversation practice request produces content that ignores
    # what the learner actually asked to practice.
    if req.unit.topic == ALPHABET_TOPIC and mix_override is None:
        alphabet_unit_note = f"""
This is the learner's very first unit in {req.target_lang} — before any vocabulary, teach the
writing system itself. Each exercise must introduce ONE letter, character, or basic sound of
{req.target_lang} (e.g. a vowel, or the most common/simplest character): what it looks like
(target_text = just that single letter/character), and its name/sound spelled out phonetically in
{req.native_lang} in native_text (e.g. for Korean ㅏ: native_text = "se pronuncia como la 'a' en
'casa'"). For audio_text, NEVER use the bare letter/character alone — a real speech engine is
trained on natural speech, not isolated letter-names, and reliably fails or produces nothing
audible for a single character on its own (confirmed in production: Korean ㅏ sent as audio_text
by itself made the text-to-speech engine fail outright). Instead audio_text MUST always be a short,
real, natural word in {req.target_lang} that starts with or clearly contains this letter/character's
sound — exactly like teaching a child phonics with "A is for Apple" rather than just the bare letter
"A". Do NOT jump ahead to full sentences or grammar — this unit is only about recognizing and
sounding out individual letters/characters through real, pronounceable example words."""

    return f"""You are a real, experienced language teacher designing a lesson, not a flashcard
generator. Generate a JSON array of exactly {len(mix)} exercises for a learner studying
{req.target_lang} (native language: {req.native_lang}), at CEFR level {req.unit.level.value},
on the topic "{req.unit.topic}".

{_difficulty_note_for_level(req.unit.level)}

COMMUNICATIVE APPROACH — this is the single most important rule in this prompt, and the one
most often ignored: a real teacher teaches a language through real communication in real
situations, not through isolated vocabulary flashcards. Concretely:
- "target_text" must be a natural phrase or short sentence a person would actually SAY in a
  real situation tied to "{req.unit.topic}" (e.g. for "Food & drink": "¿Me traes la cuenta,
  por favor?" — not the bare word "cuenta"). Single, isolated words are only acceptable when
  the topic is inherently about naming individual items (numbers, colors, the alphabet unit) —
  everywhere else, teach the word being USED, not the word in isolation.
- "image_prompt" must depict the SITUATION the phrase is used in (a person at a market stall
  handing over coins, two people greeting each other at a door), not a sterile studio photo of
  an isolated object — the picture should let a learner infer meaning from context and body
  language the way a real classroom's gestures and visual aids do, without needing a
  translation at all.
- Prefer teaching meaning through the image and the situation over the translation, even on
  levels where native_text is shown — native_text is a safety net for when context genuinely
  isn't enough, not the first or only way the learner is meant to understand the word.
- For "free_conversation_prompt" specifically: frame it as a short role-play in a concrete
  everyday situation (ordering food, asking for directions, introducing your family), the way
  a real class practices speaking without fear of being wrong — never a bare, out-of-context
  question like "Say something about food."

Write every instruction and example so a curious 7-year-old could follow it —
short, simple sentences, no unexplained jargon in the instructions themselves —
while still using the correct grammatical terms (e.g. "verbo", "adjetivo",
"pretérito") where naming a concept actually helps the learner. Simple
explanation, accurate vocabulary — not a dumbed-down one.

Personalize the example sentences and vocabulary choices around the learner's
interests where natural: {interests}. {mistakes}
{alphabet_unit_note}

Exercise types to use, in this order: {types_list}.
{show_translation}

Return ONLY a JSON array. Each element must have these exact fields:
- "type": one of {[t.value for t in ExerciseType]}
- "prompt": a short INSTRUCTION telling the learner what to do, written in {req.native_lang} for
  levels below B1, or in {req.target_lang} for B1+ (to build immersion). This is NOT a description
  of an image and NOT in English unless {req.native_lang} is English — e.g. "¿Qué imagen corresponde
  a esta palabra?" or "Elige la opción correcta.", never a sentence describing what a picture shows.
- "target_text": the key phrase or short sentence in {req.target_lang} — a real thing someone
  would say in this situation (see COMMUNICATIVE APPROACH above), not an isolated dictionary word
  unless the topic itself is about naming individual items.
- "native_text": the translation in {req.native_lang} (empty string only if translations
  are disabled for this level — see the translation rule above)
- "options": array of 3-4 answer choices in {req.target_lang} (only for
  multiple_choice and image_match; empty array otherwise)
- "correct_answer": the correct answer string
- "image_prompt": a short, concrete visual description (in English, for an image generator)
  depicting the SITUATION target_text is used in — required for image_match, optional/empty
  otherwise. This text is ONLY for the image generator — never copy it into "prompt".
- "audio_text": the {req.target_lang} text that should be spoken aloud (usually
  same as target_text)

Example of one well-formed image_match item (native_lang=es, target_lang=en) — note how
"prompt" is a short instruction and "image_prompt" is a separate, purely visual description
that never leaks into "prompt":
{{"type": "image_match", "prompt": "Elige la imagen que corresponde a esta palabra.",
"target_text": "handshake", "native_text": "apretón de manos", "options": ["handshake", "hug", "wave"],
"correct_answer": "handshake", "image_prompt": "two people shaking hands, simple flat illustration",
"audio_text": "handshake", "vocab_key": "greetings.handshake"}}
- "vocab_key": a short lowercase slug identifying this vocabulary item, stable
  across repeats (e.g. "greetings.hello")

Respond with raw JSON only, no markdown fences, no commentary."""


def build_conversation_system_prompt(
    target_lang: str, native_lang: str, level: CEFRLevel, interests: list[str], memory: str = ""
) -> str:
    interests_s = ", ".join(interests) if interests else "general topics"
    memory_note = f"LONG-TERM MEMORY OF THIS LEARNER:\n{memory}\n" if memory else ""
    level_note = (
        "Use only very simple, high-frequency vocabulary and short sentences. "
        "If the learner writes in their native language, gently reply with the "
        f"{target_lang} equivalent and encourage them to repeat it."
        if level.rank <= 1
        else "Use natural, level-appropriate vocabulary and correct mistakes gently by "
        "restating the corrected sentence before continuing the conversation."
        if level.rank <= 3
        else "Speak at a natural native pace with idioms and nuance appropriate to an "
        "advanced/native speaker, still noting any errors briefly."
    )
    return f"""You are a warm, patient, native-speaking conversation partner for a
language learner practicing {target_lang} in a live voice-call-style session.
The learner's native language is {native_lang}. Their level is {level.value}.
Their interests include: {interests_s} — steer small talk toward these when natural.

{memory_note}

Rules:
- Reply primarily in {target_lang}.
- {level_note}
- Keep replies conversational and short (1-3 sentences), like a real spoken exchange,
  and always end with a question or prompt so the conversation keeps flowing.
- If the learner made a language mistake, include a one-line gentle correction
  prefixed with "Correction:" in {native_lang}, then continue in {target_lang}.
"""
