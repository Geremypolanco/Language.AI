"""Motivation signal detection — a real, specific pattern read off a
student's own recent lesson attempts, each paired with a concrete
suggested action instead of a generic "¡sigue así!" message. Scoped to
language lesson_history: it's the one table with enough graded attempts
per student, at comparable difficulty, to see an actual trend — Academy's
quiz/exam history is sparser per course and doesn't have that shape.

Deliberately NOT fine-grained per-session fatigue detection (already
declined in predictions.py) — there's no real session-boundary tracking
in this app (lesson_history rows are just completion timestamps, not
start/end pairs), so "fatigue" would have to be guessed from gaps between
timestamps rather than measured, which is exactly the kind of fabricated
signal this app avoids.
"""

from __future__ import annotations

from .. import db

_RECENT_N = 5
_STRUGGLE_THRESHOLD = 0.5
_STRONG_THRESHOLD = 0.85
_FLAT_SPREAD = 0.15


def detect_signal(user_id: str) -> dict:
    """Looks at the student's most recent completed lessons (newest
    first). Needs at least 3 to say anything — one bad or good lesson is
    noise, not a pattern."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT score FROM lesson_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, _RECENT_N),
        )
        recent = [r["score"] for r in cur.fetchall()]

    if len(recent) < 3:
        return {"signal": "sin_datos", "message": ""}

    if all(s < _STRUGGLE_THRESHOLD for s in recent[:3]):
        return {
            "signal": "frustracion",
            "message": (
                "Los últimos ejercicios han sido difíciles — probemos con una unidad más sencilla "
                "o repasemos el vocabulario antes de seguir."
            ),
        }

    if all(s >= _STRONG_THRESHOLD for s in recent[:3]):
        return {
            "signal": "buen_momentum",
            "message": "Vienes acertando casi todo — buen momento para subir la dificultad o avanzar de unidad.",
        }

    if len(recent) >= 4 and (max(recent) - min(recent)) < _FLAT_SPREAD:
        return {
            "signal": "estancado",
            "message": "El resultado se ha mantenido parecido en los últimos intentos — prueba otro tipo de ejercicio para este tema.",
        }

    return {"signal": "neutral", "message": ""}
