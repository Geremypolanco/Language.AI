"""Learning style inference — conversation vs. written/structured
practice — inferred entirely from existing activity, never asked as an
onboarding question. Self-reported "I'm a visual learner" surveys are
exactly the kind of unverifiable input this app avoids asking for; a
ratio computed from real activity is at least measuring something true.

Deliberately excluded: visual/auditory/kinesthetic modality inference.
There's no real signal in this app linking, say, image-exercise
completion rate to "visual learner" — that's a well-known, scientifically
unsupported framework, and faking a plausible-looking classification for
it would be guessing dressed up as insight, not a real inference.
"""

from __future__ import annotations

from .. import db

# Below this much total tracked activity there isn't enough signal to
# call a ratio meaningful — a student with 2 chat turns and 1 lesson
# isn't "balanced", they just haven't done much yet.
_MIN_ACTIVITY_FOR_SIGNAL = 5


def infer_learning_style(user_id: str) -> dict:
    """conversational_count: turns the student actually sent in live tutor
    chat (conversation_log). written_count: completed lessons + graded
    academy questions + submitted assignments — every place a student
    produces a written/structured answer instead of talking. The ratio
    between the two, not either number alone, is the actual signal."""
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM conversation_log WHERE user_id=? AND role='user'", (user_id,))
        conversational = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM lesson_history WHERE user_id=?", (user_id,))
        written = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM academy_question_attempt WHERE user_id=?", (user_id,))
        written += cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM academy_assignment_submission WHERE user_id=?", (user_id,))
        written += cur.fetchone()["c"]

    total = conversational + written
    if total < _MIN_ACTIVITY_FOR_SIGNAL:
        style = "sin_datos"
    elif conversational > written * 1.5:
        style = "conversacional"
    elif written > conversational * 1.5:
        style = "estructurado"
    else:
        style = "equilibrado"

    return {"conversational_count": conversational, "written_count": written, "style": style}
