"""Intelligent Recommendations: unlike learning_engine/recommendations.py
(which only ever answers "what course next?"), this combines every signal
the Learning Intelligence Engine already computes into a richer set of
action types — review, advance, exercises, retake_exam, lab, read_material,
simulation, tutor_conversation, rest — each backed by real evidence and a
human-readable reason. No new data, no AI call: this is an orchestration
layer that calls existing learning_engine/srs/db functions and turns their
outputs into recommendation objects.

Every recommendation dict has the same shape:
    {"action": str, "target": str | None, "reason": str, "evidence": dict}
`reason` is never empty — see this package's docstring on why explaining
"why" is a requirement, not an enhancement. Callers (daily_planner.py,
routers/academy.py) can filter/rank this list; this module doesn't decide
which ones "matter most today" — that's daily_planner.py's job.
"""

from __future__ import annotations

from .. import db, srs
from ..learning_engine import competency, concept_review, motivation, predictions
from ..learning_engine import recommendations as base_recommendations
from . import concept_graph

_RETAKE_EXAM_BELOW = 0.5
_ASSIGNMENTS_PER_COURSE = 3  # academy_library/validators.py's validate_assignments enforces exactly this


def _review_recommendations(user_id: str) -> list[dict]:
    out = []
    due_concepts = concept_review.due_concepts(user_id)
    if due_concepts:
        out.append(
            {
                "action": "review",
                "target": due_concepts[0]["target_text"],
                "reason": (
                    f"Tienes {len(due_concepts)} concepto(s) académico(s) pendientes de repaso — "
                    "el sistema de repetición espaciada calcula que tu recuerdo de estos ya bajó."
                ),
                "evidence": {"due_count": len(due_concepts), "concepts": [c["target_text"] for c in due_concepts]},
            }
        )

    due_vocab = srs.due_review_items(user_id, limit=10, exclude_prefix="academic:")
    if due_vocab:
        out.append(
            {
                "action": "review",
                "target": due_vocab[0]["target_text"],
                "reason": f"Tienes {len(due_vocab)} palabra(s) de idiomas pendientes de repaso hoy.",
                "evidence": {"due_count": len(due_vocab), "words": [v["target_text"] for v in due_vocab]},
            }
        )
    return out


def _advance_and_reinforce_recommendations(user_id: str, field_id: str, course_ids_in_order: list[str], titles: dict) -> list[dict]:
    out = []
    weak = base_recommendations.courses_needing_review(user_id, field_id, course_ids_in_order)
    if weak:
        weakest = weak[0]
        comp = competency.get_competency(user_id, weakest)
        score = comp["score"] if comp else 0.0
        blocker = concept_graph.likely_root_cause(user_id, weakest)
        reason = f"Tu dominio de \"{titles.get(weakest, weakest)}\" es de {score:.0%}, por debajo del umbral recomendado."
        if blocker:
            reason += f" Probablemente necesitas reforzar antes \"{titles.get(blocker['course_id'], blocker['course_id'])}\"."
        out.append({"action": "exercises", "target": weakest, "reason": reason, "evidence": {"score": score, "blocker": blocker}})

    next_course = base_recommendations.recommend_next_course(user_id, field_id, course_ids_in_order)
    if next_course:
        out.append(
            {
                "action": "advance",
                "target": next_course,
                "reason": f"Ya completaste o dominaste el contenido anterior — el siguiente paso es \"{titles.get(next_course, next_course)}\".",
                "evidence": {"difficulty_signal": base_recommendations.difficulty_signal(user_id, next_course)},
            }
        )
    return out


def _retake_exam_recommendations(user_id: str, titles: dict) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT course_id, score, submitted_at FROM academy_quiz_submission
            WHERE user_id=? AND kind='exam' AND id IN (
                SELECT MAX(id) FROM academy_quiz_submission WHERE user_id=? AND kind='exam' GROUP BY course_id
            )
            """,
            (user_id, user_id),
        )
        latest_exams = [dict(r) for r in cur.fetchall()]

    out = []
    for exam in latest_exams:
        if exam["score"] < _RETAKE_EXAM_BELOW:
            out.append(
                {
                    "action": "retake_exam",
                    "target": exam["course_id"],
                    "reason": (
                        f"Tu último examen de \"{titles.get(exam['course_id'], exam['course_id'])}\" fue de "
                        f"{exam['score']:.0%} — vale la pena repasar y volver a presentarlo."
                    ),
                    "evidence": {"last_score": exam["score"], "submitted_at": exam["submitted_at"]},
                }
            )
    return out


def _lab_recommendations(user_id: str, course_ids_in_order: list[str], titles: dict) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT course_id, COUNT(DISTINCT assignment_id) AS n FROM academy_assignment_submission "
            "WHERE user_id=? GROUP BY course_id",
            (user_id,),
        )
        submitted_by_course = {r["course_id"]: r["n"] for r in cur.fetchall()}

    out = []
    for course_id in course_ids_in_order:
        # done > 0 is itself the "actually engaged with this course"
        # check — a course with zero submissions just hasn't come up yet,
        # not a pending lab.
        done = submitted_by_course.get(course_id, 0)
        if 0 < done < _ASSIGNMENTS_PER_COURSE:
            out.append(
                {
                    "action": "lab",
                    "target": course_id,
                    "reason": (
                        f"Has entregado {done} de {_ASSIGNMENTS_PER_COURSE} trabajos de "
                        f"\"{titles.get(course_id, course_id)}\" — te falta terminar el resto."
                    ),
                    "evidence": {"submitted": done, "total": _ASSIGNMENTS_PER_COURSE},
                }
            )
    return out


def _read_material_recommendation(user_id: str, field_id: str, course_ids_in_order: list[str], titles: dict) -> dict | None:
    weak = base_recommendations.courses_needing_review(user_id, field_id, course_ids_in_order)
    if not weak:
        return None
    course_id = weak[0]
    return {
        "action": "read_material",
        "target": course_id,
        "reason": f"Antes de practicar más, te conviene releer el contenido de \"{titles.get(course_id, course_id)}\".",
        "evidence": {"course_id": course_id},
    }


def _simulation_recommendation(user_id: str, course_ids_in_order: list[str], titles: dict) -> dict | None:
    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT course_id FROM academy_scenario_submission WHERE user_id=?", (user_id,))
        done_scenarios = {r["course_id"] for r in cur.fetchall()}

    for course_id in course_ids_in_order:
        if course_id in done_scenarios:
            continue
        if base_recommendations.difficulty_signal(user_id, course_id) == "avanzar":
            return {
                "action": "simulation",
                "target": course_id,
                "reason": f"Ya dominas \"{titles.get(course_id, course_id)}\" — es un buen momento para una simulación práctica.",
                "evidence": {"difficulty_signal": "avanzar"},
            }
    return None


def _motivation_recommendations(user_id: str) -> list[dict]:
    out = []
    signal = motivation.detect_signal(user_id)
    risk = predictions.dropout_risk(user_id)

    if signal["signal"] == "frustracion" and risk["risk_level"] == "alto":
        out.append(
            {
                "action": "rest",
                "target": None,
                "reason": "Llevas varios intentos difíciles seguidos y tu actividad reciente bajó — un descanso corto suele rendir más que forzar otra sesión ahora.",
                "evidence": {"motivation_signal": signal["signal"], "dropout_risk": risk["risk_level"]},
            }
        )
    elif signal["signal"] == "frustracion":
        out.append(
            {
                "action": "tutor_conversation",
                "target": None,
                "reason": signal["message"],
                "evidence": {"motivation_signal": signal["signal"]},
            }
        )
    return out


def generate_recommendations_without_field(user_id: str) -> list[dict]:
    """Same idea as generate_recommendations() but for a student with no
    Academy enrollment — only the signals that don't need a field/course
    list still apply: due reviews (language vocab and any academic
    concepts from a past enrollment) and motivation-driven rest/tutor
    prompts. Used by daily_planner.py so a language-only student still
    gets a real, if narrower, plan instead of an empty one."""
    recs: list[dict] = []
    recs.extend(_review_recommendations(user_id))
    recs.extend(_motivation_recommendations(user_id))
    return recs


def generate_recommendations(
    user_id: str, field_id: str, course_ids_in_order: list[str], titles: dict
) -> list[dict]:
    """The full, unranked list of everything the mentor could recommend
    right now. daily_planner.py picks and orders a short subset of this
    for "today's plan"; routers/academy.py can also expose this list
    directly for a "see everything" view."""
    recs: list[dict] = []
    recs.extend(_review_recommendations(user_id))
    recs.extend(_advance_and_reinforce_recommendations(user_id, field_id, course_ids_in_order, titles))
    recs.extend(_retake_exam_recommendations(user_id, titles))
    recs.extend(_lab_recommendations(user_id, course_ids_in_order, titles))
    read_material = _read_material_recommendation(user_id, field_id, course_ids_in_order, titles)
    if read_material:
        recs.append(read_material)
    simulation = _simulation_recommendation(user_id, course_ids_in_order, titles)
    if simulation:
        recs.append(simulation)
    recs.extend(_motivation_recommendations(user_id))
    return recs
