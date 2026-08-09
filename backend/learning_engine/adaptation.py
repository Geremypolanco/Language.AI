"""Adaptation Engine — translates one LearningState into a per-consumer,
typed decision, so each module gets a representation shaped for what it
actually needs (a paragraph of prose for Conversation; structured
priorities/weights for Curriculum/Exercises) instead of every consumer
reaching into LearningState and reinterpreting it themselves.

Conversation adapter: deliberately scoped to fields Conversation has no
other route to: routers/conversation.py already derives its tone/pacing
from mentor_engine.adaptive_mentor (itself built on the same motivation
signal LearningState carries) and already surfaces due vocabulary via srs
directly — repeating either here would just produce two overlapping,
possibly-contradictory instruction blocks in the same prompt. career_goal
and Academy frequent_mistakes are the two LearningState fields
Conversation has no other way to see today, so it surfaces exactly those
two.

Curriculum adapter: intentionally narrower than it could look at first —
Academy's frequent_mistakes is scoped to `course_id` (e.g.
"software-engineering:BACHELOR:0"), a completely different namespace from
the language track's `Unit.id` (e.g. "A1-3"); there is no mapping between
the two, so frequent_mistakes cannot drive a language-unit weight without
fabricating one. due_review_items is the only LearningState field that
carries a real language `unit_id` (see srs.due_review_items' content
snapshot), so it's the only signal for_curriculum uses. Deliberately no
negative/deprioritization weight for "already mastered" units either —
that needs unit_mastery data added to LearningState first, not a guessed
value standing in for it.

Exercises adapter: an audit of Exercise's real fields (id, type, prompt,
target_text, native_text, options, correct_answer, image_prompt,
audio_text, audio_url, vocab_key — see models.py) found exactly one join
to LearningState: `vocab_key`, matching due_review_items' vocab_key
byte-for-byte (both come from vocab_progress via srs.py) — more precise
than Curriculum's unit_id join, since it targets one exercise, not a
whole unit. Nothing else audited (hint visibility, recommended attempt
count, recommended time, a motivation_signal-driven adjustment) has a
real backing signal in this app's data model today; guessing one for any
of them would repeat the fatigue/confidence mistake this file has
avoided everywhere else, so v1 is exactly the one join with evidence,
nothing broader. Presentation-only, same as Curriculum: never reorders
or regenerates the exercise list, never touches generate_exercises()'s
cache_key or prompt (see hf_client.py's generate_exercises docstring for
exactly why that cache_key is deliberately not per-user) — it only
annotates already-resolved Exercise objects with a priority signal a
caller may use to highlight or sort, the content itself is unaffected
either way.

Only one adaptation rule exists today (the vocab_key join above), so
there's one ExerciseAdaptation, not per-pedagogical-mode variants
(Lesson/Practice/Review) — those three delivery paths do have genuinely
different constraints (see routers/lessons.py: Lessons read pre-built
library content with no cache_key at all, Practice is AI-generated and
cached, Review is already fully personalized and never cached), worth
documenting here for whoever extends this, but splitting the
*implementation* into three now would be premature: nothing has forced a
second rule to diverge from the first yet. Split when it does, not before.

Convention for the next adapter (Writing/Reading/Pronunciation/Assessment,
or a second Exercises rule that genuinely needs its own type): `def
for_<consumer>(state: LearningState) -> <Consumer>Adaptation`, its own
small frozen dataclass shaped for what that consumer actually needs —
same as the three examples above. Not codified as a typing.Protocol on
purpose: each adapter's return type is intentionally its own shape,
nothing here calls adapters polymorphically, and a Protocol typed `Any`
back wouldn't buy real static checking — just unused surface area. The
convention lives here, in prose, where the examples that establish it
already are."""

from __future__ import annotations

from dataclasses import dataclass

from .learning_state import LearningState

_MAX_MISTAKES_SURFACED = 3


@dataclass(frozen=True)
class ConversationAdaptation:
    """`instructions` is a ready-to-append block of English directives for
    the tutor's system prompt — empty string when the state has nothing
    actionable to add, so callers can append it unconditionally."""

    instructions: str


def for_conversation(state: LearningState) -> ConversationAdaptation:
    lines: list[str] = []

    if state.career_goal:
        lines.append(
            "Where it fits naturally, favor examples and vocabulary relevant to this learner's "
            f"stated goal: {state.career_goal}."
        )

    mistake_topics = [
        m["question_text"] for m in state.frequent_mistakes[:_MAX_MISTAKES_SURFACED] if m.get("question_text")
    ]
    if mistake_topics:
        lines.append(
            "This learner has repeatedly missed these points in their coursework — look for natural "
            "chances to reinforce them without turning the conversation into a quiz: " + "; ".join(mistake_topics)
        )

    if not lines:
        return ConversationAdaptation(instructions="")
    return ConversationAdaptation(instructions="\n".join(f"- {line}" for line in lines))


_DUE_REVIEW_WEIGHT = 1.0


@dataclass(frozen=True)
class CurriculumAdaptation:
    """Per-unit priority weights layered on top of the existing CEFR-ordered
    skill path — the path itself (order, availability, which units exist)
    never changes; a consumer uses these only to prioritize *within* that
    fixed structure. `weight_for` returns 0.0 (no signal, no change in
    priority) for any unit not in `unit_weights`."""

    unit_weights: dict[str, float]

    def weight_for(self, unit_id: str) -> float:
        return self.unit_weights.get(unit_id, 0.0)


def for_curriculum(state: LearningState) -> CurriculumAdaptation:
    """See module docstring for why this only reads due_review_items: it's
    the one LearningState field scoped to a real language Unit.id."""
    weights: dict[str, float] = {}
    for item in state.due_review_items:
        unit_id = item.get("unit_id")
        if not unit_id:
            continue
        weights[unit_id] = weights.get(unit_id, 0.0) + _DUE_REVIEW_WEIGHT
    return CurriculumAdaptation(unit_weights=weights)


@dataclass(frozen=True)
class ExerciseAdaptation:
    """Per-exercise priority signal, keyed by `vocab_key` — the exercise
    list itself (content, order, count) never changes; a consumer uses
    this only to annotate or sort *within* that fixed list. `priority_for`
    returns 0.0 (no signal) for any vocab_key not in `exercise_priorities`,
    including "" (an exercise with no vocab_key, e.g. free_conversation_
    prompt, never has a signal to look up)."""

    exercise_priorities: dict[str, float]

    def priority_for(self, vocab_key: str) -> float:
        if not vocab_key:
            return 0.0
        return self.exercise_priorities.get(vocab_key, 0.0)


def for_exercises(state: LearningState) -> ExerciseAdaptation:
    """See module docstring for why this is the only rule in v1: due_
    review_items' vocab_key is the one real, audited join between
    LearningState and Exercise."""
    priorities: dict[str, float] = {}
    for item in state.due_review_items:
        vocab_key = item.get("vocab_key")
        if not vocab_key:
            continue
        priorities[vocab_key] = priorities.get(vocab_key, 0.0) + _DUE_REVIEW_WEIGHT
    return ExerciseAdaptation(exercise_priorities=priorities)
