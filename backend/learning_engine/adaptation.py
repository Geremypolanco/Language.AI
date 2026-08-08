"""Adaptation Engine — translates one LearningState into a per-consumer,
typed decision, so each module gets a representation shaped for what it
actually needs (a paragraph of prose for Conversation; structured
priorities/weights for Exercises/Curriculum once those adapters exist)
instead of every consumer reaching into LearningState and reinterpreting
it themselves.

Only the Conversation adapter exists so far. It's deliberately scoped to
fields Conversation has no other route to: routers/conversation.py
already derives its tone/pacing from mentor_engine.adaptive_mentor
(itself built on the same motivation signal LearningState carries) and
already surfaces due vocabulary via srs directly — repeating either here
would just produce two overlapping, possibly-contradictory instruction
blocks in the same prompt. career_goal and Academy frequent_mistakes are
the two LearningState fields Conversation has no other way to see today,
so v1 surfaces exactly those two."""

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
