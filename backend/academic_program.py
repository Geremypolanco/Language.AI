"""Semester/credit/GPA structure for the BACHELOR academy track.

Scope note — read before extending this: the Freshman/Sophomore/Junior/
Senior class-standing system, the 8-semester/120-credit structure, and the
weighted quiz/midterm/final grading model are all real conventions of a
standard 4-year US bachelor's degree. They are deliberately applied ONLY to
`AcademicLevel.BACHELOR`. ASSOCIATE/MASTER/DOCTORATE keep the simpler
course-count-only model already in academy.py/mastery.py, because:

- Class-standing terms (Freshman..Senior) are specifically a 4-year
  bachelor's convention in the US system — applying them to a 2-year
  associate degree or a graduate program would just be wrong, not merely
  simplified.
- A "120 total credits" target is a bachelor's norm; graduate/associate
  programs use very different credit totals with no standard mapping this
  module could apply without fabricating one.

Like backend/personas.py's faculty assignment, the semester/credit/
prerequisite structure here is DETERMINISTIC — computed live from the
course's position in the field's curriculum (see routers/academy.py's
_course_id: "{field_id}:{level}:{order}") — not stored in its own table, so
it can never drift out of sync with the code that defines it. It is a
simulated structure for progress-tracking and motivation, exactly like the
faculty roster: this app issues no real credit, degree, or transcript (see
academy.py's module docstring) — a real registrar's actual prerequisite
graph and credit values are not being represented here, because this app
has no access to one and has no business fabricating a specific
institution's catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from . import db
from .models import AcademicLevel

# ── Grading ──────────────────────────────────────────────────────────────

QUIZ_WEIGHT = 0.20
MIDTERM_WEIGHT = 0.30
FINAL_WEIGHT = 0.50
PASSING_PERCENTAGE = 70.0

# Standard US 4.0-scale letter-grade cutoffs — the most common version of
# this table; exact cutoffs vary slightly by institution in reality, but
# this is the widely-documented default (used here since this app has no
# specific institution to defer to).
_GRADE_SCALE: list[tuple[float, str, float]] = [
    (97, "A+", 4.0),
    (93, "A", 4.0),
    (90, "A-", 3.7),
    (87, "B+", 3.3),
    (83, "B", 3.0),
    (80, "B-", 2.7),
    (77, "C+", 2.3),
    (73, "C", 2.0),
    (70, "C-", 1.7),
    (67, "D+", 1.3),
    (63, "D", 1.0),
    (60, "D-", 0.7),
    (0, "F", 0.0),
]


def letter_grade_for(percentage: float) -> str:
    for cutoff, letter, _points in _GRADE_SCALE:
        if percentage >= cutoff:
            return letter
    return "F"


def gpa_points_for(letter: str) -> float:
    for _cutoff, candidate, points in _GRADE_SCALE:
        if candidate == letter:
            return points
    raise ValueError(f"Unknown letter grade: {letter!r}")


def compute_final_percentage(
    quiz_score: float | None, midterm_score: float | None, final_score: float | None
) -> float | None:
    """None (not a fabricated 0) until all three weighted components exist —
    a course with no final exam yet has no final grade, full stop."""
    if quiz_score is None or midterm_score is None or final_score is None:
        return None
    return quiz_score * QUIZ_WEIGHT + midterm_score * MIDTERM_WEIGHT + final_score * FINAL_WEIGHT


# ── Program structure ───────────────────────────────────────────────────

TOTAL_BACHELOR_CREDITS = 120
COURSES_PER_SEMESTER = 3  # AcademicLevel.BACHELOR.course_count (24) / 8 semesters
TOTAL_SEMESTERS = 8

_CLASS_STANDINGS: list[tuple[int, str]] = [
    (0, "Freshman"),
    (31, "Sophomore"),
    (61, "Junior"),
    (91, "Senior"),
]


def class_standing_for(credits_earned: int) -> str:
    standing = _CLASS_STANDINGS[0][1]
    for threshold, name in _CLASS_STANDINGS:
        if credits_earned >= threshold:
            standing = name
    return standing


@dataclass(frozen=True)
class ProgramCourse:
    course_id: str
    order: int
    semester: int
    credits: int
    kind: str  # "core" | "elective" — the last course of each semester is an elective


def _credits_for_course(order: int, total_courses: int, target_total_credits: int) -> int:
    """Distributes target_total_credits across total_courses as evenly as
    possible, putting any remainder on the later (more advanced) courses."""
    base = target_total_credits // total_courses
    remainder = target_total_credits % total_courses
    return base + (1 if order >= total_courses - remainder else 0)


def build_program_structure(field_id: str) -> list[ProgramCourse]:
    """The full 8-semester BACHELOR structure for a field — deterministic,
    always the same for the same field_id, computed live (see module
    docstring for why this isn't a persisted table)."""
    total_courses = AcademicLevel.BACHELOR.course_count
    courses = []
    for order in range(total_courses):
        semester = order // COURSES_PER_SEMESTER + 1
        credits = _credits_for_course(order, total_courses, TOTAL_BACHELOR_CREDITS)
        kind = "elective" if (order + 1) % COURSES_PER_SEMESTER == 0 else "core"
        course_id = f"{field_id}:{AcademicLevel.BACHELOR.value}:{order}"
        courses.append(ProgramCourse(course_id=course_id, order=order, semester=semester, credits=credits, kind=kind))
    return courses


def parse_course_id(course_id: str) -> tuple[str, AcademicLevel, int]:
    field_id, level_value, order_str = course_id.split(":")
    return field_id, AcademicLevel(level_value), int(order_str)


def is_course_unlocked(user_id: str, course_id: str) -> bool:
    """A course's semester is unlocked once every course in the PRIOR
    semester has been passed (final_percentage >= PASSING_PERCENTAGE) — a
    semester-level gate, not a fabricated arbitrary per-course prerequisite
    graph this app has no real catalog to justify. Semester 1 is always
    unlocked."""
    field_id, level, order = parse_course_id(course_id)
    if level != AcademicLevel.BACHELOR:
        return True  # the simpler course-count model has no gating at all
    structure = build_program_structure(field_id)
    this_course = next(c for c in structure if c.order == order)
    if this_course.semester == 1:
        return True
    prior_semester_courses = [c for c in structure if c.semester == this_course.semester - 1]
    with db.cursor() as cur:
        placeholders = ",".join("?" for _ in prior_semester_courses)
        cur.execute(
            f"SELECT course_id, passed FROM academy_course_progress "
            f"WHERE user_id=? AND course_id IN ({placeholders})",
            (user_id, *[c.course_id for c in prior_semester_courses]),
        )
        passed_map = {r["course_id"]: bool(r["passed"]) for r in cur.fetchall()}
    return all(passed_map.get(c.course_id, False) for c in prior_semester_courses)


# ── Grade recording ──────────────────────────────────────────────────────


def record_grade_component(
    user_id: str,
    course_id: str,
    quiz_score: float | None = None,
    midterm_score: float | None = None,
    final_score: float | None = None,
) -> dict:
    """Merges any provided score(s) into the course's existing record (a
    quiz can be submitted before the midterm exists yet), then recomputes
    the weighted final only once all three are present. Returns the
    updated row as a dict."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT quiz_score, midterm_score, final_score FROM academy_course_progress "
            "WHERE user_id=? AND course_id=?",
            (user_id, course_id),
        )
        existing = cur.fetchone()

    quiz = quiz_score if quiz_score is not None else (existing["quiz_score"] if existing else None)
    midterm = midterm_score if midterm_score is not None else (existing["midterm_score"] if existing else None)
    final = final_score if final_score is not None else (existing["final_score"] if existing else None)

    final_percentage = compute_final_percentage(quiz, midterm, final)
    letter_grade = letter_grade_for(final_percentage) if final_percentage is not None else None
    gpa_points = gpa_points_for(letter_grade) if letter_grade is not None else None
    passed = final_percentage is not None and final_percentage >= PASSING_PERCENTAGE
    completed_at = datetime.now(UTC).isoformat() if passed else None

    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO academy_course_progress
                   (user_id, course_id, completed_at, quiz_score, midterm_score, final_score,
                    final_percentage, letter_grade, gpa_points, passed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, course_id) DO UPDATE SET
                   completed_at=excluded.completed_at, quiz_score=excluded.quiz_score,
                   midterm_score=excluded.midterm_score, final_score=excluded.final_score,
                   final_percentage=excluded.final_percentage, letter_grade=excluded.letter_grade,
                   gpa_points=excluded.gpa_points, passed=excluded.passed""",
            (
                user_id,
                course_id,
                completed_at or "",
                quiz,
                midterm,
                final,
                final_percentage,
                letter_grade,
                gpa_points,
                1 if passed else 0,
            ),
        )

    return {
        "course_id": course_id,
        "quiz_score": quiz,
        "midterm_score": midterm,
        "final_score": final,
        "final_percentage": final_percentage,
        "letter_grade": letter_grade,
        "gpa_points": gpa_points,
        "passed": passed,
    }


# ── Progress + graduation ETA ────────────────────────────────────────────


def compute_program_progress(user_id: str, field_id: str) -> dict:
    structure = build_program_structure(field_id)
    total_credits = sum(c.credits for c in structure)
    course_ids = [c.course_id for c in structure]

    with db.cursor() as cur:
        placeholders = ",".join("?" for _ in course_ids)
        cur.execute(
            f"SELECT course_id, passed, gpa_points FROM academy_course_progress "
            f"WHERE user_id=? AND course_id IN ({placeholders}) AND passed=1",
            (user_id, *course_ids),
        )
        passed_rows = cur.fetchall()

    passed_ids = {r["course_id"] for r in passed_rows}
    credits_earned = sum(c.credits for c in structure if c.course_id in passed_ids)
    gpa_points = [r["gpa_points"] for r in passed_rows if r["gpa_points"] is not None]

    return {
        "field_id": field_id,
        "credits_earned": credits_earned,
        "total_credits": total_credits,
        "percent_complete": round((credits_earned / total_credits) * 100, 1) if total_credits else 0.0,
        "class_standing": class_standing_for(credits_earned),
        "gpa": round(sum(gpa_points) / len(gpa_points), 2) if gpa_points else None,
        "courses_passed": len(passed_ids),
        "total_courses": len(structure),
    }


def estimate_graduation(user_id: str, field_id: str) -> dict:
    """Real math from actual completion timestamps — never a fabricated
    ETA. Returns has_enough_data=False (not a guessed number) when there
    isn't a completion history to compute a velocity from."""
    structure = build_program_structure(field_id)
    total_credits = sum(c.credits for c in structure)
    course_ids = [c.course_id for c in structure]

    with db.cursor() as cur:
        placeholders = ",".join("?" for _ in course_ids)
        cur.execute(
            f"SELECT course_id, completed_at FROM academy_course_progress "
            f"WHERE user_id=? AND course_id IN ({placeholders}) AND passed=1 AND completed_at != ''",
            (user_id, *course_ids),
        )
        rows = cur.fetchall()

    credits_by_course = {c.course_id: c.credits for c in structure}
    credits_earned = sum(credits_by_course[r["course_id"]] for r in rows)
    remaining_credits = total_credits - credits_earned

    if remaining_credits <= 0:
        return {"has_enough_data": True, "months_remaining": 0.0, "humanized": "Ya completaste todos los créditos."}

    if len(rows) < 2:
        return {"has_enough_data": False, "months_remaining": None, "humanized": None}

    timestamps = sorted(datetime.fromisoformat(r["completed_at"]) for r in rows)
    span_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400
    if span_days <= 0:
        return {"has_enough_data": False, "months_remaining": None, "humanized": None}

    velocity_credits_per_month = credits_earned / (span_days / 30.44)
    if velocity_credits_per_month <= 0:
        return {"has_enough_data": False, "months_remaining": None, "humanized": None}

    months_remaining = remaining_credits / velocity_credits_per_month
    return {
        "has_enough_data": True,
        "months_remaining": round(months_remaining, 1),
        "velocity_credits_per_month": round(velocity_credits_per_month, 2),
        "humanized": _humanize_months(months_remaining),
    }


def _humanize_months(months: float) -> str:
    total_days = round(months * 30.44)
    years, rem_days = divmod(total_days, 365)
    semesters, days = divmod(rem_days, 182)  # ~6 months per semester
    parts = []
    if years:
        parts.append(f"{years} año{'s' if years != 1 else ''}")
    if semesters:
        parts.append(f"{semesters} semestre{'s' if semesters != 1 else ''}")
    if days and not years:
        parts.append(f"{days} día{'s' if days != 1 else ''}")
    if not parts:
        parts.append("menos de un semestre")
    return f"Te faltan {', '.join(parts)} para graduarte al ritmo actual."


# ── Next step / remediation ──────────────────────────────────────────────


def get_next_step(user_id: str, field_id: str) -> dict:
    """Business rule: a failed or in-progress-but-incomplete course in the
    CURRENT semester blocks advancement and points at AI tutoring for that
    specific course (see routers/academy.py's /ask endpoint) instead of the
    next course — never silently skips a failed course."""
    structure = build_program_structure(field_id)
    course_ids = [c.course_id for c in structure]

    with db.cursor() as cur:
        placeholders = ",".join("?" for _ in course_ids)
        cur.execute(
            f"SELECT course_id, final_percentage, passed FROM academy_course_progress "
            f"WHERE user_id=? AND course_id IN ({placeholders})",
            (user_id, *course_ids),
        )
        graded = {r["course_id"]: r for r in cur.fetchall()}

    for course in structure:
        row = graded.get(course.course_id)
        if row and row["final_percentage"] is not None and not row["passed"]:
            return {
                "action": "remediate",
                "course_id": course.course_id,
                "semester": course.semester,
                "final_percentage": row["final_percentage"],
                "message": (
                    f"No aprobaste el curso {course.course_id} "
                    f"({row['final_percentage']:.1f}%, se necesita {PASSING_PERCENTAGE:.0f}%). "
                    "Habla con tu profesor(a) de IA sobre este curso antes de continuar."
                ),
            }

    for course in structure:
        if course.course_id not in graded or not graded[course.course_id]["passed"]:
            if is_course_unlocked(user_id, course.course_id):
                return {"action": "advance", "course_id": course.course_id, "semester": course.semester}
            return {
                "action": "remediate",
                "course_id": course.course_id,
                "semester": course.semester,
                "final_percentage": None,
                "message": (
                    f"Completa todos los cursos del semestre {course.semester - 1} "
                    "antes de continuar."
                ),
            }

    return {"action": "graduated", "course_id": None, "semester": None}
