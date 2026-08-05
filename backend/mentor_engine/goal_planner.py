"""Goal Planner: breaks a free-text learning goal into concrete, ordered
milestones — "Convertirme en AI Engineer" -> "Aprender Python", "Dominar
Algoritmos", "Aprender Machine Learning", "Construir proyectos",
"Preparar entrevistas" — generated once, on demand, and persisted on the
goal row (learning_engine/goals.py's milestones column), never
regenerated unless the goal is deleted and re-added. Reuses academy_
library.generators._generate_validated — the exact retry-and-validate
loop the Academy content pipeline already runs — instead of writing a
second one.

This is legitimately dynamic, personalized content, not shared course
content that has to be pre-generated for every student (see academy_
library/__init__.py and language_library/__init__.py's "content belongs
to the course, not the user" principle): a goal is inherently per-user
and typically added once, so generating it the one time it's actually
needed costs nothing extra and is never repeated for the same goal.

Deliberately NOT curriculum-aware yet: a goal that happens to match the
student's actual Academy enrollment (e.g. "terminar mi carrera de
Ciencias de la Computación") could in principle get REAL milestones from
that field's actual course sequence instead of an AI-generated guess —
but deciding whether a free-text goal "matches" an enrollment needs
either the student explicitly linking the two or a fuzzy-matching step
that risks silently mismatching them. Neither exists yet; this is a
clean extension point (a future ensure_milestones could check for a
linked field before falling back to generate_milestones) that doesn't
require changing this module's public interface.
"""

from __future__ import annotations

from ..academy_library.generators import GenerationError, _clean_json, _generate_validated
from ..learning_engine import goals

_MIN_MILESTONES = 3
_MAX_MILESTONES = 8
_MAX_MILESTONE_LEN = 80


def _validate_milestones(data: object) -> list[str]:
    if not isinstance(data, list) or not (_MIN_MILESTONES <= len(data) <= _MAX_MILESTONES):
        return [f"expected {_MIN_MILESTONES}-{_MAX_MILESTONES} milestones, got {data!r}"]
    problems: list[str] = []
    seen: set[str] = set()
    for i, m in enumerate(data):
        if not isinstance(m, str) or not m.strip():
            problems.append(f"milestone {i} is empty")
            continue
        if len(m) > _MAX_MILESTONE_LEN:
            problems.append(f"milestone {i} is too long")
        key = m.strip().lower()
        if key in seen:
            problems.append(f"milestone {i} duplicates an earlier one")
        seen.add(key)
    return problems


def _build_prompt(goal_text: str) -> str:
    return f"""A student has this learning goal: "{goal_text}"

Break it down into 3 to 8 concrete, ordered milestones — short, concise
steps (each under 10 words) that lead from where they are now to
achieving this goal, in the order they should be tackled.

Output ONLY a JSON array of strings, nothing else. Example, for the goal
"Become an AI Engineer":
["Learn Python fundamentals", "Master data structures and algorithms", "Learn machine learning fundamentals", "Build real ML projects", "Prepare for technical interviews"]
"""


async def generate_milestones(goal_text: str) -> list[str]:
    prompt = _build_prompt(goal_text)

    def parse_and_validate(raw: str) -> tuple[list[str], list[str]]:
        data = _clean_json(raw)
        return data, _validate_milestones(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=400, temperature=0.5)


async def ensure_milestones(user_id: str, goal_id: int) -> list[str]:
    """Returns the goal's milestones, generating and persisting them once
    if they don't exist yet. Falls back to a single milestone — the
    goal's own text — if generation fails after every retry, so a
    transient AI outage never leaves a goal permanently un-trackable.
    That fallback is the honest "we couldn't break this down further"
    case, not a fabricated breakdown."""
    goal = goals.get_goal(user_id, goal_id)
    if goal is None:
        raise ValueError(f"no such goal: {goal_id}")
    if goal["milestones"]:
        return goal["milestones"]

    try:
        milestones = await generate_milestones(goal["text"])
    except GenerationError:
        milestones = [goal["text"]]

    goals.set_milestones(user_id, goal_id, milestones)
    return milestones
