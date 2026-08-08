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

Convention for the next adapter (Exercises, or a future Writing/Reading/
Pronunciation/Assessment module): `def for_<consumer>(state: LearningState)
-> <Consumer>Adaptation`, its own small frozen dataclass shaped for what
that consumer actually needs — same as for_conversation/for_curriculum
above. Not codified as a typing.Protocol on purpose: each adapter's return
type is intentionally its own shape (prose for one, weights for another),
nothing here calls adapters polymorphically, and a Protocol typed `Any`
back wouldn't buy real static checking — just unused surface area. The
convention lives here, in prose, where the two examples that establish it
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
