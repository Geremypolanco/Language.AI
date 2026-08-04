"""The learning engine: everything downstream of the pre-generated academic
and language libraries that's about understanding, measuring, and
accelerating a student's learning rather than generating or serving static
content. See each submodule's docstring for its own scope:

- knowledge_graph.py: concepts (from each course's glossary) and the
  relations between them/their courses.
- competency.py: per-user, per-course mastery scores (Academy) plus
  get_language_competencies/get_unified_competencies, which reuse
  backend/srs.py's unit_mastery instead of a second scoring table.
- recommendations.py: which course to study next, specialization
  suggestions, and a difficulty-band signal — all from real
  competency/knowledge-graph data, never generated content.
- achievements.py: real, skill-backed milestones derived from competency
  and completion data — never a cosmetic-only badge.
- concept_review.py: spaced-repetition review of academic concepts,
  reusing the exact SM-2 engine backend/srs.py already runs for language
  vocabulary.
- analytics.py: student-facing progress summary, plus a field-wide
  aggregate function (admin-facing data, deliberately not wired to an
  HTTP endpoint — see its own docstring on why).
- portfolio.py: aggregates real submitted work (assignments, scenarios,
  completed courses) and attaches each item's real competency score.
- student_profile.py: the unified "Learning Intelligence" dashboard —
  combines every module below into one profile_summary() call.
- goals.py: multiple, ordered learning goals (CRUD on learning_goal).
- predictions.py: forgetting/dropout risk and time-to-mastery — plain,
  documented heuristics, explicitly NOT a trained ML model (see its
  own docstring for why one isn't possible here).
- learning_style.py: conversational-vs-written practice ratio, inferred
  from real activity, never asked at onboarding.
- motivation.py: a specific, non-generic signal ("frustracion",
  "buen_momentum", "estancado") from a student's own recent lessons.

Deliberately NOT here, across every batch this package was built in (see
each submodule's own docstring for the specific reasoning): a simulations
engine, large randomized per-student question banks, a persistent
tutor-memory subsystem beyond backend/personas.py's conversation memory
and this package's own goals/career_goal, an admin-facing HTTP endpoint
for analytics.field_summary (no admin-role system exists in this app), a
fabricated "probability of passing" score, fine-grained per-session
fatigue detection (no real session-boundary data exists to measure it
from), and visual/auditory/kinesthetic learning-style inference (an
unvalidated pop-psychology framework this app won't fake). Each would be
guessing dressed up as a real feature; the modules above only ever surface
something the platform can actually, honestly measure.
"""
