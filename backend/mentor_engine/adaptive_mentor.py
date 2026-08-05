"""Adaptive Mentor: turns the Learning Intelligence Engine's existing
motivation and difficulty signals into a concrete tutoring-behavior
directive instead of leaving every conversation at one fixed tone
regardless of how the student is actually doing:

- "apoyo" (frustration detected, or a course flagged "reforzar"): divide
  goals into smaller steps, simplify explanations, add more examples.
- "reto" (strong momentum, or a course flagged "avanzar"): open-ended
  problems, real cases instead of textbook ones, less introductory
  theory, higher difficulty.
- "neutral": no real signal either way — no adjustment forced.

No new signal is computed here: mode selection reads straight from
learning_engine.motivation.detect_signal and learning_engine.
recommendations.difficulty_signal, the exact functions the rest of the
mentor engine already uses for the same underlying data.
"""

from __future__ import annotations

from ..learning_engine import motivation
from ..learning_engine import recommendations as base_recommendations

_SUPPORT_DIRECTIVES = [
    "divide cualquier objetivo en pasos más pequeños",
    "usa explicaciones más simples y directas",
    "da más ejemplos concretos antes de pedir que practique solo",
]
_CHALLENGE_DIRECTIVES = [
    "plantea problemas abiertos en vez de ejercicios guiados",
    "usa casos reales en vez de ejemplos de libro de texto",
    "reduce la teoría introductoria — ve directo a la práctica",
    "sube la dificultad de lo que le pides",
]


def get_mentor_mode(user_id: str, course_id: str | None = None) -> dict:
    """course_id is optional: motivation is always available (it only
    needs lesson history), while the difficulty_signal fallback needs a
    specific course to grade standing on — pass it when the caller has
    one (e.g. inside a specific course's chat), omit it for general
    conversation practice."""
    signal = motivation.detect_signal(user_id)
    if signal["signal"] == "frustracion":
        return {"mode": "apoyo", "directives": _SUPPORT_DIRECTIVES, "evidence": {"motivation_signal": signal["signal"]}}
    if signal["signal"] == "buen_momentum":
        return {"mode": "reto", "directives": _CHALLENGE_DIRECTIVES, "evidence": {"motivation_signal": signal["signal"]}}

    if course_id:
        difficulty = base_recommendations.difficulty_signal(user_id, course_id)
        if difficulty == "reforzar":
            return {"mode": "apoyo", "directives": _SUPPORT_DIRECTIVES, "evidence": {"difficulty_signal": difficulty}}
        if difficulty == "avanzar":
            return {"mode": "reto", "directives": _CHALLENGE_DIRECTIVES, "evidence": {"difficulty_signal": difficulty}}

    return {"mode": "neutral", "directives": [], "evidence": {}}


def mode_instruction_text(mode_result: dict) -> str:
    """Renders a mode as a short instruction block a system prompt can
    append verbatim — see routers/conversation.py's existing "ADAPTIVE
    TONE" section, which this sits next to rather than replaces: that one
    reacts to the tone of the CURRENT message, this one reacts to the
    student's broader trend across sessions. Empty string for "neutral"
    — nothing to inject when there's no real signal to act on."""
    if not mode_result["directives"]:
        return ""
    bullets = "\n".join(f"- {d}" for d in mode_result["directives"])
    return f"### ADAPTIVE MENTOR MODE ({mode_result['mode'].upper()}):\n{bullets}"
