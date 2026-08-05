"""AI Mentor Engine — the orchestrator that ties every module in this
package (plus the pre-existing Learning Intelligence Engine) into one
coherent "brain." It doesn't store anything of its own or compute a new
signal beyond what the modules below already provide — it reads,
combines, and prioritizes.

Modules (see each one's own docstring for what it does and doesn't do):
- knowledge_profile.py — per-concept mastery map (Unknown/Learning/
  Practicing/Mastered/Expert), from real SM-2 review state.
- concept_graph.py — blocker detection at both course level (curriculum-
  order edges, zero AI cost) and concept level (real "depends_on" edges
  academy_library.generators.generate_concept_relations extracts per
  course at build time — scripts/build_academy.py), reusing learning_
  engine.knowledge_graph's edges either way.
- recommendation_engine.py — 9 action types (review/advance/exercises/
  retake_exam/lab/read_material/simulation/tutor_conversation/rest),
  each with a reason + evidence — nothing opaque, ever.
- daily_planner.py — curates recommendation_engine's output into a
  short, ordered "today" plan.
- insights.py — post-session, comparative observations (improvement,
  struggle, mistake concentration, ready-to-advance).
- adaptive_mentor.py — a tutoring-behavior directive ("apoyo"/"reto")
  derived from motivation + difficulty signals, wired into the live
  conversation system prompt (routers/conversation.py).
- conversation_memory_adapter.py — read-only accessor over the existing
  tutor-chat memory (user_memories), for continuity across sessions.
- goal_planner.py — breaks a free-text goal into ordered milestones,
  generated once and persisted (learning_engine/goals.py).

Every one of these reuses the pre-existing Learning Intelligence Engine
(backend/learning_engine/) rather than tracking anything twice — this
package adds decision-making and orchestration on top, not new state.

Scalability: every function here takes plain data in and returns plain
dicts/lists out — no module holds a reference to another's internals.
That's deliberate: swapping knowledge_profile's rule-based status buckets
for embeddings-based similarity, concept_graph's extracted depends_on
edges for a vector-similarity knowledge graph, recommendation_engine's
rule-based scoring for a learned ranking model, or adding a multi-agent
reasoning layer that calls several of these modules and arbitrates
between their outputs — none of that requires changing this module's
public functions' signatures, only what happens inside the module being
upgraded.

Deliberately NOT built yet (see each submodule's own docstring for the
specific reasoning): embeddings/vector similarity anywhere in this
package, a trained recommendation-ranking model, curriculum-aware goal
milestones for a goal that happens to match the student's enrollment,
and a multi-agent reasoning layer. All four are explicitly designed-for
extension points (see "Scalability" above), not missing pieces bolted on
as an afterthought — none of them can be validated as real today without
either labeled outcome data (a ranking/prediction model) or an explicit
goal-to-field link the student hasn't been asked to provide (curriculum-
aware milestones).
"""

from __future__ import annotations

from ..learning_engine import competency, goals, predictions
from . import adaptive_mentor, daily_planner, insights, knowledge_profile, recommendation_engine


def get_mentor_dashboard(
    user_id: str,
    field_id: str | None,
    course_ids_in_order: list[str],
    titles: dict,
    level=None,
) -> dict:
    """The single call routers/academy.py's dashboard endpoint makes —
    combines every mentor_engine module plus the pre-existing Learning
    Intelligence Engine into one response. field_id/course_ids_in_order
    may be empty for a student with no Academy enrollment; every section
    below stays real (if narrower) instead of raising, matching
    student_profile.profile_summary's precedent."""
    has_field = bool(field_id and course_ids_in_order)

    if has_field:
        recommendations = recommendation_engine.generate_recommendations(
            user_id, field_id, course_ids_in_order, titles
        )
        mentor_insights = insights.generate_insights(user_id, field_id, course_ids_in_order, titles)
        knowledge = knowledge_profile.get_knowledge_profile(user_id, field_id)
        strengths_weaknesses = competency.strengths_and_weaknesses(user_id, field_id)
    else:
        recommendations = recommendation_engine.generate_recommendations_without_field(user_id)
        mentor_insights = []
        knowledge = []
        strengths_weaknesses = {"strengths": [], "weaknesses": []}

    unified_competencies = competency.get_unified_competencies(user_id, field_id)
    daily_plan = daily_planner.build_daily_plan(user_id, field_id, course_ids_in_order, titles, level)
    mode = adaptive_mentor.get_mentor_mode(user_id)
    forgetting_risk = predictions.forgetting_risk(user_id)
    dropout_risk = predictions.dropout_risk(user_id)

    mastered_concepts = [c for c in knowledge if c["status"] in ("mastered", "expert")]
    weak_concepts = [c for c in knowledge if c["status"] in ("unknown", "learning")]

    all_goals = goals.list_goals(user_id)
    next_milestones = [
        {"goal_id": g["id"], "goal_text": g["text"], "current_milestone": g["current_milestone"]}
        for g in all_goals
        if g["current_milestone"] is not None
    ]

    return {
        "status": {"mentor_mode": mode["mode"]},
        "goals": all_goals,
        "next_milestones": next_milestones,
        "competencies": unified_competencies,
        "mastered_concepts": mastered_concepts,
        "weak_concepts": weak_concepts,
        "strengths_and_weaknesses": strengths_weaknesses,
        "recommendations": recommendations,
        "daily_plan": daily_plan,
        "insights": mentor_insights,
        "risks": {"forgetting_risk": forgetting_risk, "dropout_risk": dropout_risk},
    }
