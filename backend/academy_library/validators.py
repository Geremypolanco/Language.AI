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
