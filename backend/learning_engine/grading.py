"""Grades one quiz/exam submission: multiple_choice/true_false are graded
deterministically (the stored correct_answer), open/applied_problem
questions are graded by the AI against their rubric_note (hf_client.
grade_open_answer). Rolls everything into one 0..1 score, which the caller
(routers/academy.py) feeds into competency.record_result.
"""

from __future__ import annotations

from ..hf_client import hf_client


def _normalize(value: object) -> str:
    return str(value).strip().lower()


async def grade_submission(questions: list[dict], answers: dict[str, str], native_lang: str) -> dict:
    """`answers` maps a question's index (as a string key, matching how it
    arrives over JSON) to the student's given answer. A question with no
    given answer is graded as wrong, not skipped — an unanswered question
    is not a free pass."""
    results = []
    for i, q in enumerate(questions):
        given = answers.get(str(i), "")
        qtype = q.get("type")
        if qtype in ("multiple_choice", "true_false"):
            correct = _normalize(given) == _normalize(q.get("correct_answer"))
            results.append({"correct": correct, "feedback": ""})
        else:  # open, applied_problem
            passed, feedback = await hf_client.grade_open_answer(
                q.get("question", ""), q.get("rubric_note", ""), given, native_lang
            )
            results.append({"correct": passed, "feedback": feedback})

    score = sum(1 for r in results if r["correct"]) / len(results) if results else 0.0
    return {"score": score, "results": results}
