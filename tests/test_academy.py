from backend.academy import (
    build_assignments_prompt,
    build_course_prompt,
    build_curriculum_prompt,
    build_practice_scenario_prompt,
    get_field,
)
from backend.models import AcademicLevel


def test_academy_prompts_all_carry_the_child_clarity_instruction():
    # Regression: build_course_prompt and build_assignments_prompt already
    # had a "clear enough for a young learner" instruction, but
    # build_curriculum_prompt and build_practice_scenario_prompt didn't —
    # inconsistent across the same content pipeline.
    field = get_field("nursing-foundations")
    level = AcademicLevel.BACHELOR
    prompts = [
        build_curriculum_prompt(field, level.label_es, level.course_count, "es"),
        build_course_prompt(field, level.label_es, "Anatomía I", "desc", "es"),
        build_practice_scenario_prompt(field, level.label_es, "Anatomía I", "desc", "es"),
        build_assignments_prompt(field, level.label_es, "Anatomía I", "desc", "es"),
    ]
    for prompt in prompts:
        assert "7-year-old" in prompt


def test_academy_curriculum_depth_scales_with_level():
    field = get_field("nursing-foundations")
    associate_prompt = build_curriculum_prompt(field, AcademicLevel.ASSOCIATE.label_es, AcademicLevel.ASSOCIATE.course_count, "es")
    master_prompt = build_curriculum_prompt(field, AcademicLevel.MASTER.label_es, AcademicLevel.MASTER.course_count, "es")
    assert AcademicLevel.ASSOCIATE.label_es in associate_prompt
    assert AcademicLevel.MASTER.label_es in master_prompt
    assert str(AcademicLevel.ASSOCIATE.course_count) in associate_prompt
    assert str(AcademicLevel.MASTER.course_count) in master_prompt
