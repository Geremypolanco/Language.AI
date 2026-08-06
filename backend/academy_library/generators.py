"""Calls the AI model to produce each academy content type, validates the
result (academy_library.validators), and retries a bounded number of times
before giving up if Hugging Face/the chat model produces invalid output.

Distinct from hf_client.py's existing generate_curriculum/generate_course_
content/generate_assignments/generate_practice_scenario: those serve the
legacy on-demand-generate-and-disk-cache path that routers/academy.py still
falls back to for any (field, level) the build pipeline hasn't covered yet
(see build.py's module docstring for why that fallback exists). The
functions here are pipeline-only: they are never disk-cached themselves
(the caller — build.py — is responsible for persisting the validated result
through an AcademyStore) and they raise GenerationError instead of quietly
returning filler/placeholder content, since a build-time failure should
surface loudly in the build log rather than silently publish something that
looks like a real course but isn't.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Callable

from .. import academy
from ..hf_client import hf_client
from . import validators

if TYPE_CHECKING:
    from ..models import AcademicField, AcademicLevel, CEFRLevel

_MAX_ATTEMPTS = 3


class GenerationError(Exception):
    """Raised when a content type still fails validation after every retry."""


def _clean_json(raw: str) -> Any:
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


async def _generate_validated(
    prompt: str,
    parse_and_validate: Callable[[str], tuple[Any, list[str]]],
    *,
    max_tokens: int,
    temperature: float = 0.6,
) -> Any:
    """Shared retry loop: calls the model, hands the raw text to
    `parse_and_validate` (which must return (data, problems) — problems
    empty means success), and retries up to _MAX_ATTEMPTS times on either a
    parse exception or a non-empty problems list. Raises GenerationError
    with the last attempt's problems once every attempt is exhausted."""
    last_problems: list[str] = ["no attempt made"]
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = await hf_client.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            data, problems = parse_and_validate(raw)
        except Exception as exc:  # JSON parse failure, network failure, etc.
            data, problems = None, [f"attempt {attempt} raised {exc!r}"]
        if not problems:
            return data
        last_problems = problems
    raise GenerationError(f"failed after {_MAX_ATTEMPTS} attempts: {'; '.join(last_problems)}")


async def generate_curriculum(
    field: "AcademicField", level: "AcademicLevel", native_lang: str, course_count: int,
    cefr_level: "CEFRLevel | None" = None,
) -> dict:
    prompt = academy.build_curriculum_prompt(field, level.label_es, course_count, native_lang, cefr_level)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        items = _clean_json(raw)
        data = {
            "courses": [
                {"title": i.get("title", ""), "description": i.get("description", "")}
                for i in items
                if i.get("title")
            ]
        }
        return data, validators.validate_curriculum(data, min_courses=max(1, course_count // 2))

    return await _generate_validated(prompt, parse_and_validate, max_tokens=1600, temperature=0.5)


async def generate_course_content(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> dict:
    prompt = academy.build_course_prompt(field, level.label_es, course_title, course_description, native_lang, cefr_level)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        items = _clean_json(raw)
        data = {
            "modules": [
                {"title": i.get("title", ""), "content": i.get("content", "")}
                for i in items
                if i.get("content")
            ]
        }
        return data, validators.validate_course_content(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=1800, temperature=0.6)


async def generate_glossary(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> dict:
    prompt = academy.build_glossary_prompt(field, level.label_es, course_title, course_description, native_lang, cefr_level=cefr_level)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_glossary(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=900)


async def generate_quiz(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> dict:
    prompt = academy.build_quiz_prompt(field, level.label_es, course_title, course_description, native_lang, cefr_level=cefr_level)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_quiz(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=1400)


async def generate_exam(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
    exam_kind: str = "final", cefr_level: "CEFRLevel | None" = None,
) -> dict:
    prompt = academy.build_exam_prompt(field, level.label_es, course_title, course_description, native_lang, exam_kind, cefr_level=cefr_level)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_exam(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=2200)


async def generate_assignments(
    field: "AcademicField", level: "AcademicLevel", course_id: str, course_title: str, course_description: str,
    native_lang: str, cefr_level: "CEFRLevel | None" = None,
) -> list[dict]:
    prompt = academy.build_assignments_prompt(field, level.label_es, course_title, course_description, native_lang, cefr_level=cefr_level)

    def parse_and_validate(raw: str) -> tuple[list[dict], list[str]]:
        items = _clean_json(raw)
        data = [
            {
                "id": f"{course_id}:{i}",
                "type": item.get("type", "tarea"),
                "title": item.get("title", ""),
                "instructions": item.get("instructions", ""),
            }
            for i, item in enumerate(items)
            if item.get("instructions")
        ]
        return data, validators.validate_assignments(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=1800, temperature=0.6)


async def generate_scenario(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
    cefr_level: "CEFRLevel | None" = None,
) -> str:
    prompt = academy.build_practice_scenario_prompt(field, level.label_es, course_title, course_description, native_lang, cefr_level=cefr_level)

    def parse_and_validate(raw: str) -> tuple[str, list[str]]:
        return raw, validators.validate_scenario(raw)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=500, temperature=0.8)


# ── Curriculum Engine Phase 1: metadata, prerequisite graph, biography ───


async def generate_course_metadata(
    field: "AcademicField", level: "AcademicLevel", course_title: str, course_description: str, native_lang: str,
) -> dict:
    prompt = academy.build_course_metadata_prompt(field, level.label_es, course_title, course_description, native_lang)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_course_metadata(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=900, temperature=0.4)


async def generate_prerequisite_graph(
    field: "AcademicField", level: "AcademicLevel", native_lang: str, courses: list[dict],
) -> dict:
    """courses: [{"title": ..., "description": ...}, ...] in curriculum
    order — same shape as a persisted curriculum.json's "courses" list."""
    prompt = academy.build_prerequisite_graph_prompt(field, level.label_es, courses, native_lang)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_prerequisite_graph(data, len(courses))

    return await _generate_validated(prompt, parse_and_validate, max_tokens=900, temperature=0.4)


async def generate_tutor_biography(field: "AcademicField", native_lang: str) -> dict:
    prompt = academy.build_tutor_biography_prompt(field, native_lang)

    def parse_and_validate(raw: str) -> tuple[dict, list[str]]:
        data = _clean_json(raw)
        return data, validators.validate_tutor_biography(data)

    return await _generate_validated(prompt, parse_and_validate, max_tokens=700, temperature=0.7)
