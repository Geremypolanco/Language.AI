"""LearningState — the single canonical, typed snapshot of what the app
knows about one student, assembled exclusively from data that already has
a real function producing it elsewhere in learning_engine/srs.

This is deliberately NOT the place new signals get invented. Every field
must trace back to one existing function; if there's no real function
backing a candidate field, it stays out of v1 rather than being fabricated
here (see learning_engine.motivation's fatigue precedent for why: a
guessed signal is worse than no signal in a system other modules make
decisions from). Fields that could plausibly be added later — fatigue, a
numeric confidence score, estimated_cefr — need their own measured data
source first, not just a slot in this model.

Consumers should get this through LearningStateProvider below rather than
calling build_learning_state directly on every request — see its
docstring for why."""

from __future__ import annotations

import threading
import time

from pydantic import BaseModel

from .. import db, srs
from . import competency, learning_style, motivation, predictions
from .student_profile import frequent_mistakes as _frequent_mistakes
from .student_profile import get_career_goal

STATE_VERSION = 1


class LearningState(BaseModel):
    """See module docstring — every field here is sourced from one existing
    learning_engine/srs function, named alongside it below."""

    user_id: str
    version: int = STATE_VERSION
    generated_at: str

    # competency.get_unified_competencies — academy + language competencies side by side.
    competencies: dict
    # predictions.forgetting_risk / dropout_risk — the app's existing risk models.
    forgetting_risk: dict
    dropout_risk: dict
    # learning_style.infer_learning_style — inferred from real exercise-type performance spread.
    learning_style: dict
    # student_profile.get_career_goal — the one field the student states directly.
    career_goal: str
    # student_profile.frequent_mistakes — this student's own repeated wrong Academy answers,
    # scoped to field_id; empty (not fabricated) when there's no Academy enrollment.
    frequent_mistakes: list[dict]
    # srs.due_review_items — vocabulary genuinely due for spaced-repetition review right now,
    # excluding academic-concept keys (see concept_review.py) so this stays language-scoped.
    due_review_items: list[dict]
    # motivation.detect_signal — frustracion/buen_momentum/estancado/neutral/sin_datos,
    # read off the student's own last few graded lessons.
    motivation_signal: dict


def build_learning_state(user_id: str, field_id: str | None = None) -> LearningState:
    """Assembles one LearningState from the functions listed on each field
    above. `field_id` is optional exactly like student_profile.profile_
    summary's — most LearningState consumers (Conversation, Practice)
    aren't Academy-scoped, so the Academy-only fields degrade to empty
    rather than erroring."""
    return LearningState(
        user_id=user_id,
        generated_at=db.now_iso(),
        competencies=competency.get_unified_competencies(user_id, field_id),
        forgetting_risk=predictions.forgetting_risk(user_id),
        dropout_risk=predictions.dropout_risk(user_id),
        learning_style=learning_style.infer_learning_style(user_id),
        career_goal=get_career_goal(user_id),
        frequent_mistakes=_frequent_mistakes(user_id, field_id) if field_id else [],
        due_review_items=srs.due_review_items(user_id, limit=5, exclude_prefix="academic:"),
        motivation_signal=motivation.detect_signal(user_id),
    )


class LearningStateProvider:
    """A small in-process, per-user TTL cache in front of build_learning_
    state — every consumer (Conversation today; Exercises/Curriculum/
    dashboard as they're wired in later) asks the same provider for the
    same user's state within a short window instead of each re-running
    ~6 DB queries per call. Not Redis: this app has no other shared-cache
    dependency (see config.py's zero-hosting-cost approach), and a single
    process already serves every request on the one machine this runs on.

    TTL default is short (5 min) on purpose — long enough to cover the
    several turns of one Talk/practice session without recomputing every
    turn, short enough that a change made mid-session (answering an SRS
    review, finishing a course) shows up again soon rather than being
    stuck stale for the rest of the process's life."""

    _DEFAULT_TTL_S = 300.0

    def __init__(self, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, LearningState]] = {}

    def get(self, user_id: str, field_id: str | None = None, *, force_refresh: bool = False) -> LearningState:
        cache_key = f"{user_id}:{field_id or ''}"
        now = time.monotonic()
        if not force_refresh:
            with self._lock:
                cached = self._cache.get(cache_key)
            if cached is not None and (now - cached[0]) < self._ttl_s:
                return cached[1]

        state = build_learning_state(user_id, field_id)
        with self._lock:
            self._cache[cache_key] = (now, state)
        return state

    def invalidate(self, user_id: str) -> None:
        """Drops every cached state (any field_id) for one user — for a
        caller that just changed something LearningState reflects (e.g.
        after grading a quiz) and wants the next `get()` to see it
        immediately instead of waiting out the TTL."""
        prefix = f"{user_id}:"
        with self._lock:
            for key in [k for k in self._cache if k.startswith(prefix)]:
                del self._cache[key]

    def reset(self) -> None:
        """Test-only: drops every cached state for every user. The module-
        level singleton below lives for the whole process, so a test suite
        whose fixtures give each test a fresh database (see
        tests/conftest.py) still needs this — without it, a later test
        reusing a common id like "u1" could silently read an earlier
        test's stale, already-torn-down state instead of computing its own."""
        with self._lock:
            self._cache.clear()


# Process-wide singleton — same pattern as hf_client.hf_client (backend/hf_client.py).
learning_state_provider = LearningStateProvider()
