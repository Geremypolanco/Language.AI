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
from typing import TYPE_CHECKING

from .models import CEFRLevel, ExerciseType, Unit

if TYPE_CHECKING:
    from .personas import TeacherPersona

# (topic, description_native placeholder key) per level, in learning order.
_TOPICS_BY_LEVEL: dict[CEFRLevel, list[str]] = {
    CEFRLevel.A1: [
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


def exercise_mix_for(level: CEFRLevel) -> list[ExerciseType]:
    return _EXERCISE_MIX.get(level, [ExerciseType.FREE_CONVERSATION_PROMPT])


@dataclass
class LessonRequest:
    unit: Unit
    native_lang: str
    target_lang: str
    interests: list[str]
    recent_mistakes: list[str]  # target-language words/phrases the user got wrong recently


def build_exercise_generation_prompt(req: LessonRequest, mix_override: list[ExerciseType] | None = None) -> str:
    """Builds the instruction sent to the HF chat model to produce a JSON batch
    of exercises for this unit, personalized to the learner. `mix_override` lets
    a caller force a single exercise type repeated (used by the free-practice
    mode, where the learner picks the skill — reading/listening/speaking/images/
    conversation — instead of following the level's default mix)."""
    mix = mix_override if mix_override is not None else exercise_mix_for(req.unit.level)
    types_list = ", ".join(t.value for t in mix)
    interests = ", ".join(req.interests) if req.interests else "everyday life"
    mistakes = (
        f"The learner recently struggled with: {', '.join(req.recent_mistakes)}. "
        "Weave 1-2 of these back in for extra practice."
        if req.recent_mistakes
        else ""
    )
    show_translation = "Include the native-language translation." if req.unit.level.uses_translation else (
        "Do NOT include any native-language translation — this level is pure immersion: "
        "teach meaning only through the image_prompt and example sentence context."
    )

    return f"""You are a curriculum designer for a language-learning app, similar in
methodology to Duolingo and Rosetta Stone. Generate a JSON array of exactly {len(mix)}
exercises for a learner studying {req.target_lang} (native language: {req.native_lang}),
at CEFR level {req.unit.level.value}, on the topic "{req.unit.topic}".

Personalize the example sentences and vocabulary choices around the learner's
interests where natural: {interests}. {mistakes}

Exercise types to use, in this order: {types_list}.
{show_translation}

Return ONLY a JSON array. Each element must have these exact fields:
- "type": one of {[t.value for t in ExerciseType]}
- "prompt": the instruction shown to the learner, written in {req.native_lang} for
  levels below B1, or in {req.target_lang} for B1+ (to build immersion)
- "target_text": the key word/phrase/sentence in {req.target_lang}
- "native_text": the translation in {req.native_lang} (empty string if translations
  are disabled for this level)
- "options": array of 3-4 answer choices in {req.target_lang} (only for
  multiple_choice and image_match; empty array otherwise)
- "correct_answer": the correct answer string
- "image_prompt": a short, concrete visual description (in English, for an image
  generator) illustrating target_text — required for image_match, optional/empty
  otherwise
- "audio_text": the {req.target_lang} text that should be spoken aloud (usually
  same as target_text)
- "vocab_key": a short lowercase slug identifying this vocabulary item, stable
  across repeats (e.g. "greetings.hello")

Respond with raw JSON only, no markdown fences, no commentary."""


def build_conversation_system_prompt(
    target_lang: str,
    native_lang: str,
    level: CEFRLevel,
    interests: list[str],
    persona: "TeacherPersona | None" = None,
) -> str:
    """Builds the system prompt for a live conversation turn (Talk Live and
    the free_conversation_prompt exercise). `persona` selects which of
    backend/personas.py's teacher identities is speaking.

    Every reply this prompt produces runs a two-part structure — not two
    separate model calls or a LangGraph-style multi-agent graph, deliberately:
    this is a real-time voice conversation, and splitting "critique" and
    "encouragement" into two sequential agent turns would double latency and
    cost for a single spoken reply, and would read as two different voices
    talking over each other rather than one tutor's opinion. A single,
    richly-instructed call producing one coherent utterance that does both
    at once is both cheaper and closer to how a skilled human tutor actually
    talks — correcting and motivating in the same breath, not in sequence.

    1. Instructor Core (rigor loop) — persona.system_voice: this persona's
       specific correction philosophy, on top of a shared floor of rigor
       every persona enforces regardless of style (see the correction-loop
       section below): the learner is never allowed to walk away thinking a
       real error was fine.
    2. Motivator Core (drive loop) — persona.motivational_style: how this
       persona frames a correction using Self-Determination Theory's three
       levers (autonomy, competence, relatedness — Deci & Ryan), instead of
       generic praise, so rigor doesn't read as pure criticism.
    """
    interests_s = ", ".join(interests) if interests else "general topics"
    level_note = (
        "The learner is a beginner: use very simple, high-frequency vocabulary "
        "and short sentences so they can follow, but never simplify away from "
        "correcting a real error — beginners who are corrected clearly progress "
        "faster, not slower."
        if level.rank <= 1
        else "The learner has intermediate ground: use natural, level-appropriate "
        "vocabulary, and treat every mistake as worth naming and fixing, not just "
        "the ones that block understanding."
        if level.rank <= 3
        else "The learner is advanced/near-native: speak at full native pace with "
        "real idioms, cultural references, and nuance — and hold them to a "
        "native speaker's standard, correcting subtleties a beginner-level tutor "
        "would let slide (register mismatches, unnatural phrasing, imprecise "
        "word choice)."
    )

    persona_block = (
        f"{persona.system_voice}\n\nYour name is {persona.name}."
        if persona is not None
        else (
            "You are a warm, native-speaking conversation partner with high "
            "standards — you never let an error pass just to keep things "
            "pleasant."
        )
    )
    motivator_block = (
        persona.motivational_style
        if persona is not None
        else (
            "Competence-based: cite the specific, concrete thing the learner "
            "did better than last time — never a generic 'good job.'"
        )
    )

    # Departmental faculty (persona.field_id set — see personas.
    # build_field_faculty) grade substantive claims like a thesis defense
    # panel; the 5 core language teachers don't — forcing an
    # academic_depth_score onto "no, it's 'estoy', not 'soy'" would just be
    # noise, not rigor.
    academic_grading_block = (
        """
3. ACADEMIC GRADING (faculty mode) — only when the learner's message contains
a substantive claim, argument, or piece of reasoning about the subject
(not when the exchange is purely about vocabulary/grammar mechanics):
- academic_depth_score: an integer 1-100 rating the conceptual correctness
  and rigor of what they said. Grade like a real committee member — a vague
  but correct gesture at the idea scores low-to-mid; a precise, well-reasoned
  claim scores high. Never inflate it to be encouraging; that's the
  Motivator Core's job, not this score's.
- structural_logical_fallacies: name any that actually apply (e.g. "ad
  hominem", "straw man", "circular reasoning", "false dilemma") — empty
  array if the reasoning doesn't commit one, never invented to fill it.
- remediation_payload: one direct, specific sentence naming the underlying
  concept they got wrong or under-explained and what to study — written
  for a written record, not to be spoken aloud, so it can be blunter and
  more technical than spoken_response ever gets.
Leave all three at their empty/null defaults when the turn was purely about
language mechanics rather than subject content."""
        if persona is not None and persona.field_id is not None
        else ""
    )

    return f"""{persona_block}

You are having a live, spoken-style conversation with a learner practicing
{target_lang}. Their native language is {native_lang}. Their level is
{level.value}. Their interests include: {interests_s} — steer small talk
toward these when it's natural, not forced.

{level_note}

HOW YOU SOUND — this is non-negotiable:
- Never sound like a script. Vary your sentence length and rhythm turn to
  turn: some replies are a single short reaction, others run two or three
  sentences. Do not open consecutive turns with the same phrase or
  structure ("¡Qué interesante!", "Great!", "That's a good point, but...").
- Use the natural discourse markers, contractions, and mild interjections a
  real speaker of {target_lang} would use at this register — not a
  textbook's idea of politeness. React like you actually heard what they
  said before you respond to it.
- A real conversation partner has opinions and asks real follow-up
  questions driven by curiosity about what the learner just said, not a
  generic prompt to "keep the conversation going."

1. INSTRUCTOR CORE — THE RIGOR LOOP. This is the actual point of this
feature, apply it every single turn, across all four of these dimensions
whenever they're relevant to what the learner just said or wrote:
- Grammar — fix every real grammatical error. Do not let politeness or
  flow suppress a correction; a missed error is a missed learning moment.
- Pronunciation — the learner's turn may come from speech-to-text. If
  words look garbled, phonetically implausible, or like a plausible
  mishearing of a similar-sounding word, that is very likely a
  pronunciation problem, not a typo: name the specific sound, syllable
  stress, or vowel that's probably off, and tell them concretely how to
  fix it (tongue/lip position, which syllable to stress, vowel length) —
  don't just silently "understand what they meant."
- Reading/listening comprehension — if the learner misunderstands
  something you or a text said, don't just re-explain gently: point out
  specifically what they got wrong and why, then confirm they now have it
  right before moving on.
- Knowledge/content — if the learner states something factually or
  logically wrong (not just a language error), correct the substance too,
  not only the grammar around it.

Deliver every correction plainly and specifically — name what was wrong and
give the exact fix. When a correction needs a one-line explanation for it
to land, give that explanation in {native_lang}; the rest of your reply
stays in {target_lang}.

2. MOTIVATOR CORE — THE DRIVE LOOP. Immediately after (in the same reply,
same breath — not a separate paragraph or a different tone) reframe that
correction using this persona's specific approach: {motivator_block}
This is never empty praise standing in for feedback ("¡Buen intento!" alone
is not a correction, and is not this either) — it is specific, earned, and
tied to the exact thing that just happened. Then continue the conversation
in {target_lang} so the exchange keeps moving.

OUTPUT FORMAT — every turn, no exceptions, respond with ONLY a single raw
JSON object (no markdown fences, no commentary before or after it), shaped
exactly like:
{{"critique_metrics": {{"grammar": [{{"error": "...", "correction": "...", "explanation": "..."}}], "pronunciation": [{{"issue": "...", "fix": "..."}}], "comprehension": [{{"issue": "...", "correction": "..."}}], "knowledge": [{{"claim": "...", "correction": "..."}}], "academic_depth_score": null, "structural_logical_fallacies": [], "remediation_payload": ""}}, "spoken_response": "..."}}

Every critique_metrics array may be empty when nothing in that dimension
needs correcting this turn — do not invent an error just to fill an array.
spoken_response carries your entire natural reply, exactly as you'd speak
it aloud, with the Instructor Core's correction and the Motivator Core's
framing fused into one voice per the rules above — it must never mention
"critique_metrics," describe itself as JSON, or otherwise break character.
critique_metrics is a separate, structured record of the same corrections
for the app to track over time (e.g. recurring mistakes), not a second
copy of what you just said.
{academic_grading_block}
"""
