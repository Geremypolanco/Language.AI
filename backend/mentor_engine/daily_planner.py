"""Daily Learning Plan: curates recommendation_engine's full recommendation
list — plus two language-specific signals it doesn't cover — into a
short, ordered set of concrete actions for right now: the "Hoy deberías…"
list from the request. This module doesn't compute any new signal; it
only orders and caps what already-real recommendations exist, the way a
mentor triages a long list of possible next steps down to what's worth
doing today. Every item it returns still carries recommendation_engine's
own `reason`/`evidence` — nothing here is added without justification.
"""

from __future__ import annotations

from .. import db
from ..curriculum import topic_es, units_for_level
from ..models import CEFRLevel
from . import recommendation_engine

_MAX_PLAN_ITEMS = 5
# Priority order for which action categories make the cut when there are
# more real recommendations than room in the plan — matches how a mentor
# would triage: don't let "move forward" crowd out an overdue review or a
# half-finished lab.
_PRIORITY = [
    "rest", "review", "lab", "retake_exam", "tutor_conversation",
    "exercises", "read_material", "simulation", "advance",
]


def _rank(rec: dict) -> int:
    return _PRIORITY.index(rec["action"]) if rec["action"] in _PRIORITY else len(_PRIORITY)


def _language_next_unit(user_id: str, level: CEFRLevel) -> dict | None:
    """The earliest not-yet-mastered unit in the student's current CEFR
    level — the language-side equivalent of recommend_next_course, reusing
    the same unit_mastery table lessons.py's /path already reads from."""
    units = units_for_level(level)
    if not units:
        return None
    with db.cursor() as cur:
        cur.execute("SELECT unit_id FROM unit_mastery WHERE user_id=? AND mastered=1", (user_id,))
        mastered = {r["unit_id"] for r in cur.fetchall()}
    for unit in units:
        if unit.id not in mastered:
            return {
                "action": "advance",
                "target": unit.id,
                "reason": f"Tu siguiente lección de idiomas disponible es \"{topic_es(unit.topic)}\".",
                "evidence": {"unit_id": unit.id},
            }
    return None


def _conversation_practice_recommendation(user_id: str) -> dict | None:
    """Only fires when the student genuinely hasn't talked to the tutor
    today — a real, checkable fact (conversation_log), not a standing
    "practice more!" filler shown regardless of what already happened."""
    today = db.today_str()
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM conversation_log WHERE user_id=? AND role='user' AND created_at LIKE ?",
            (user_id, f"{today}%"),
        )
        today_turns = cur.fetchone()["c"]
    if today_turns > 0:
        return None
    return {
        "action": "tutor_conversation",
        "target": None,
        "reason": "Todavía no has practicado conversación hoy — unos minutos de práctica oral ayudan a fijar el vocabulario reciente.",
        "evidence": {"today_turns": today_turns},
    }


def build_daily_plan(
    user_id: str,
    field_id: str | None,
    course_ids_in_order: list[str],
    titles: dict,
    level: CEFRLevel | None,
) -> list[dict]:
    """field_id/course_ids_in_order may be empty for a student with no
    Academy enrollment — the plan then leans entirely on the language-
    side items, same "partial but real" behavior as student_profile.
    profile_summary. level may be None if the caller has no user record
    on hand yet (defensive; routers always have it)."""
    recs: list[dict] = []
    if field_id and course_ids_in_order:
        recs.extend(recommendation_engine.generate_recommendations(user_id, field_id, course_ids_in_order, titles))
    else:
        recs.extend(recommendation_engine.generate_recommendations_without_field(user_id))

    if level is not None:
        next_unit = _language_next_unit(user_id, level)
        if next_unit:
            recs.append(next_unit)

    conversation_rec = _conversation_practice_recommendation(user_id)
    if conversation_rec:
        recs.append(conversation_rec)

    # A "rest" recommendation only ever fires alongside high dropout risk
    # (see recommendation_engine._motivation_recommendations) — when it's
    # present it's the whole plan, not one item among five, since more
    # content is exactly what the evidence says not to push right now.
    for rec in recs:
        if rec["action"] == "rest":
            return [rec]

    seen_actions: set[str] = set()
    plan: list[dict] = []
    for rec in sorted(recs, key=_rank):
        if rec["action"] in seen_actions:
            continue
        seen_actions.add(rec["action"])
        plan.append(rec)
        if len(plan) >= _MAX_PLAN_ITEMS:
            break
    return plan
