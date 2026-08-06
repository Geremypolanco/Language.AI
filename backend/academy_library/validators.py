"""Content-quality gates the build pipeline runs before persisting anything
AI-generated — see build.py. Each validator returns a list of human-readable
problems; an empty list means the content passed.

Plain functions over already-parsed dicts, not Pydantic models: a Pydantic
model raises on the first bad field, but a validator here should collect
every problem in one pass so a build log actually explains what was wrong
with a rejected generation instead of just "it didn't match the schema."
"""

from __future__ import annotations

_MIN_DESCRIPTION_LEN = 10
_MIN_MODULE_CONTENT_LEN = 80
_MIN_SCENARIO_LEN = 40
_VALID_TRUE_FALSE = (True, False, "true", "false", "verdadero", "falso")
_VALID_ASSIGNMENT_TYPES = ("tarea", "informe", "proyecto")


def validate_curriculum(data: dict, min_courses: int = 1) -> list[str]:
    problems: list[str] = []
    courses = data.get("courses") if isinstance(data, dict) else None
    if not isinstance(courses, list) or len(courses) < min_courses:
        return [f"expected at least {min_courses} courses, got {courses!r}"]
    for i, c in enumerate(courses):
        if not isinstance(c, dict):
            problems.append(f"course {i} is not an object")
            continue
        if not (c.get("title") or "").strip():
            problems.append(f"course {i} has an empty title")
        if len((c.get("description") or "").strip()) < _MIN_DESCRIPTION_LEN:
            problems.append(f"course {i} description is too short")
    return problems


def validate_course_content(data: dict, min_modules: int = 2) -> list[str]:
    problems: list[str] = []
    modules = data.get("modules") if isinstance(data, dict) else None
    if not isinstance(modules, list) or len(modules) < min_modules:
        return [f"expected at least {min_modules} modules, got {modules!r}"]
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            problems.append(f"module {i} is not an object")
            continue
        if not (m.get("title") or "").strip():
            problems.append(f"module {i} has an empty title")
        if len((m.get("content") or "").strip()) < _MIN_MODULE_CONTENT_LEN:
            problems.append(f"module {i} content is too short")
    return problems


def validate_glossary(data: dict, min_terms: int = 5) -> list[str]:
    problems: list[str] = []
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, list) or len(terms) < min_terms:
        return [f"expected at least {min_terms} terms, got {terms!r}"]
    for i, t in enumerate(terms):
        if not isinstance(t, dict) or not (t.get("term") or "").strip() or not (t.get("definition") or "").strip():
            problems.append(f"glossary entry {i} is missing a term or definition")
    return problems


def _validate_questions(questions, min_questions: int, context: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(questions, list) or len(questions) < min_questions:
        return [f"{context}: expected at least {min_questions} questions, got {questions!r}"]
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            problems.append(f"{context} question {i} is not an object")
            continue
        if not (q.get("question") or "").strip():
            problems.append(f"{context} question {i} has an empty prompt")
        qtype = q.get("type")
        if qtype == "multiple_choice":
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 2:
                problems.append(f"{context} question {i} (multiple_choice) needs at least 2 options")
            if not (q.get("correct_answer") or "").strip():
                problems.append(f"{context} question {i} (multiple_choice) has no correct_answer")
        elif qtype == "true_false":
            if q.get("correct_answer") not in _VALID_TRUE_FALSE:
                problems.append(f"{context} question {i} (true_false) has an invalid correct_answer")
        elif qtype in ("open", "applied_problem"):
            if not (q.get("rubric_note") or "").strip():
                problems.append(f"{context} question {i} ({qtype}) is missing a rubric_note to grade it against")
        else:
            problems.append(f"{context} question {i} has an unknown type {qtype!r}")
    return problems


def validate_quiz(data: dict, min_questions: int = 4) -> list[str]:
    questions = data.get("questions") if isinstance(data, dict) else None
    return _validate_questions(questions, min_questions, "quiz")


def validate_exam(data: dict, min_questions: int = 8) -> list[str]:
    questions = data.get("questions") if isinstance(data, dict) else None
    problems = _validate_questions(questions, min_questions, "exam")
    if not isinstance(data, dict) or not (data.get("rubric") or "").strip():
        problems.append("exam is missing an overall rubric")
    return problems


def validate_assignments(data: list, expected_count: int = 3) -> list[str]:
    if not isinstance(data, list) or len(data) != expected_count:
        return [f"expected exactly {expected_count} assignments, got {data!r}"]
    problems: list[str] = []
    for i, a in enumerate(data):
        if not isinstance(a, dict):
            problems.append(f"assignment {i} is not an object")
            continue
        if a.get("type") not in _VALID_ASSIGNMENT_TYPES:
            problems.append(f"assignment {i} has an invalid type {a.get('type')!r}")
        if not (a.get("title") or "").strip():
            problems.append(f"assignment {i} has an empty title")
        if len((a.get("instructions") or "").strip()) < _MIN_DESCRIPTION_LEN:
            problems.append(f"assignment {i} instructions are too short")
    return problems


def validate_scenario(text: str) -> list[str]:
    if not isinstance(text, str) or len(text.strip()) < _MIN_SCENARIO_LEN:
        length = len(text.strip()) if isinstance(text, str) else "n/a"
        return [f"scenario text is too short ({length} chars)"]
    return []


# ── Curriculum Engine Phase 1: metadata, prerequisite graph, biography ───

_VALID_BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
_VALID_DIFFICULTIES = ("beginner", "intermediate", "advanced")
_VALID_COGNITIVE_LOADS = ("low", "medium", "high")


def validate_course_metadata(data: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["expected a metadata object"]

    for list_field in (
        "learning_objectives", "prerequisite_concepts", "required_vocabulary",
        "expected_competencies", "practical_outcomes",
    ):
        value = data.get(list_field)
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
            problems.append(f"{list_field} must be a non-empty list of non-empty strings")

    if data.get("bloom_level") not in _VALID_BLOOM_LEVELS:
        problems.append(f"bloom_level must be one of {_VALID_BLOOM_LEVELS}, got {data.get('bloom_level')!r}")
    if data.get("difficulty") not in _VALID_DIFFICULTIES:
        problems.append(f"difficulty must be one of {_VALID_DIFFICULTIES}, got {data.get('difficulty')!r}")
    if data.get("cognitive_load") not in _VALID_COGNITIVE_LOADS:
        problems.append(f"cognitive_load must be one of {_VALID_COGNITIVE_LOADS}, got {data.get('cognitive_load')!r}")

    hours = data.get("estimated_hours")
    if not isinstance(hours, int) or isinstance(hours, bool) or not (0 < hours <= 200):
        problems.append(f"estimated_hours must be a realistic positive integer, got {hours!r}")

    if not (data.get("assessment_strategy") or "").strip():
        problems.append("assessment_strategy must not be empty")

    return problems


def validate_prerequisite_graph(data: dict, course_count: int) -> list[str]:
    problems: list[str] = []
    prereqs = data.get("prerequisites") if isinstance(data, dict) else None
    if not isinstance(prereqs, list):
        return [f"expected a 'prerequisites' list, got {prereqs!r}"]
    for i, item in enumerate(prereqs):
        if not isinstance(item, dict):
            problems.append(f"prerequisite {i} is not an object")
            continue
        course_index, requires_index = item.get("course_index"), item.get("requires_index")
        for name, idx in (("course_index", course_index), ("requires_index", requires_index)):
            if not isinstance(idx, int) or isinstance(idx, bool) or not (0 <= idx < course_count):
                problems.append(f"prerequisite {i} has an invalid {name} {idx!r} (course_count={course_count})")
        if course_index == requires_index:
            problems.append(f"prerequisite {i} references itself (course_index == requires_index)")
    return problems


def validate_tutor_biography(data: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["expected a biography object"]

    highlights = data.get("career_highlights")
    if not isinstance(highlights, list) or len(highlights) < 2 or not all(
        isinstance(h, str) and h.strip() for h in highlights
    ):
        problems.append("career_highlights must be a list of at least 2 non-empty strings")

    for text_field in ("philosophy", "correction_focus", "system_voice", "motivational_style"):
        if len((data.get(text_field) or "").strip()) < _MIN_DESCRIPTION_LEN:
            problems.append(f"{text_field} is missing or too short")

    return problems
