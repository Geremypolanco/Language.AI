"""The learning engine: everything downstream of the pre-generated academic
library (backend/academy_library/) that's about understanding, measuring,
and accelerating a student's learning rather than generating or serving
static content. See each submodule's docstring for its own scope:

- knowledge_graph.py: concepts (from each course's glossary) and the
  relations between them/their courses.
- competency.py: per-user, per-course mastery scores, updated from graded
  quiz/exam submissions.
- recommendations.py: which course a learner should study next, given
  their competency scores and the knowledge graph's prerequisite order.
- achievements.py: real, skill-backed milestones derived from competency
  and completion data — never a cosmetic-only badge.
- concept_review.py: spaced-repetition review of academic concepts,
  reusing the exact SM-2 engine backend/srs.py already runs for language
  vocabulary.

Deliberately NOT here (see the commit message / conversation for the full
reasoning on each): a simulations engine, an automatic portfolio, large
randomized per-student question banks, a persistent tutor-memory subsystem
beyond what backend/personas.py's conversation memory already does, and an
admin-wide analytics dashboard. Each is a substantial subsystem in its own
right; building shallow, unvalidated versions of all of them in the same
pass as this one would cost more than it's worth before the foundation
here (the knowledge graph + competency model everything else would sit on
top of) is even proven out.
"""
