"""Evaluation Router — grades a learner's own free-form work (open-answer
quiz/exam questions, submitted assignments, ungraded practice-scenario
responses):

    Evaluation -> Evaluation Router -> ideal model

Reuses the CHAT model chain rather than a distinct judge model — see
registry.py's AITask.EVALUATION entry for why a second model call isn't
worth the extra latency/budget for this task today. Kept as its own router
(rather than folding straight into LLMRouter) so that decision is explicit
and swappable later without touching every grading call site."""

from __future__ import annotations

from ...hf_client import hf_client
from ..registry import AITask, chain_for


class EvaluationRouter:
    @property
    def active_chain(self):
        return chain_for(AITask.EVALUATION)

    async def grade_open_answer(
        self, question: str, rubric_note: str, student_answer: str, native_lang: str
    ) -> tuple[bool, str]:
        return await hf_client.grade_open_answer(question, rubric_note, student_answer, native_lang)

    async def grade_assignment_submission(
        self, assignment_title: str, instructions: str, response: str, native_lang: str
    ) -> dict:
        return await hf_client.grade_assignment_submission(assignment_title, instructions, response, native_lang)

    async def grade_practice_response(self, scenario: str, user_response: str, native_lang: str) -> str:
        return await hf_client.grade_practice_response(scenario, user_response, native_lang)
