"""Domain models for Lingua: users, curriculum units, exercises, progress."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CEFRLevel(StrEnum):
    """Common European Framework levels, plus NATIVE as the final rung."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    NATIVE = "NATIVE"

    @property
    def rank(self) -> int:
        return list(CEFRLevel).index(self)

    @property
    def next(self) -> "CEFRLevel":
        levels = list(CEFRLevel)
        idx = levels.index(self)
        return levels[min(idx + 1, len(levels) - 1)]

    @property
    def uses_translation(self) -> bool:
        """Rosetta-Stone style: A1 is pure immersion (image+audio+target text, no
        translation shown). From A2 on we start surfacing translations/explanations."""
        return self.rank > 0

    @property
    def allows_free_conversation(self) -> bool:
        return self.rank >= list(CEFRLevel).index(CEFRLevel.B1)


class ExerciseType(StrEnum):
    # A self-paced, ungraded teaching card shown immediately before the
    # graded exercise that tests the same vocab_key — see
    # hf_client._with_teaching_intros. Never produced directly by the AI
    # prompt; always synthesized in Python from the graded exercise it
    # precedes, so the two are always about the same word by construction.
    VOCAB_INTRO = "vocab_intro"
    IMAGE_MATCH = "image_match"  # Rosetta-Stone style: pick the image for the target word/audio
    LISTEN_TYPE = "listen_type"  # hear audio, type what you heard
    TRANSLATE_TO_TARGET = "translate_to_target"
    TRANSLATE_TO_NATIVE = "translate_to_native"
    MULTIPLE_CHOICE = "multiple_choice"
    SPEAK_REPEAT = "speak_repeat"  # record yourself repeating a phrase (STT-graded)
    FILL_BLANK = "fill_blank"
    FREE_CONVERSATION_PROMPT = "free_conversation_prompt"


class VocabItem(BaseModel):
    target_text: str
    native_text: str
    image_prompt: str
    example_sentence_target: str
    example_sentence_native: str


class Exercise(BaseModel):
    id: str
    type: ExerciseType
    prompt: str
    target_text: str
    native_text: str = ""
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    image_prompt: str = ""
    audio_text: str = ""
    audio_url: str = ""
    vocab_key: str = ""


class Unit(BaseModel):
    id: str
    topic: str
    level: CEFRLevel
    order: int
    title_native: str
    description_native: str


class UserProfile(BaseModel):
    id: str
    display_name: str
    native_lang: str
    target_lang: str
    level: CEFRLevel = CEFRLevel.A1
    interests: list[str] = Field(default_factory=list)
    xp: int = 0
    streak_days: int = 0
    gems: int = 0
    streak_freezes: int = 0
    daily_goal_minutes: int = 15
    created_at: str = ""
    last_active_date: str = ""
    tutor_persona_id: str = ""


class PersonaInfo(BaseModel):
    """Public-facing view of a backend.personas.TeacherPersona — leaves out
    the raw system/voice/portrait prompts, which are prompt-engineering
    internals rather than something the picker UI needs to display."""

    id: str
    name: str
    title: str
    philosophy: str
    correction_focus: str
    portrait_url: str


class AnswerSubmission(BaseModel):
    exercise_id: str
    unit_id: str
    vocab_key: str = ""
    given_answer: str
    correct: bool


class ProgressSnapshot(BaseModel):
    user_id: str
    xp: int
    streak_days: int
    gems: int
    streak_freezes: int
    level: CEFRLevel
    due_reviews: int
    units_mastered: int
    daily_goal_minutes: int
    today_minutes: int


class LevelMastery(BaseModel):
    level: CEFRLevel
    mastered: int
    total: int


class ActivityDay(BaseModel):
    date: str
    lessons_completed: int


class RecentLesson(BaseModel):
    unit_id: str
    topic: str
    topic_es: str
    score: float
    completed_at: str


class LeaderboardEntry(BaseModel):
    rank: int
    display_name: str
    weekly_xp: int
    is_you: bool = False


class TopicMastery(BaseModel):
    """One cell of the Progress tab's knowledge heatmap — level is 0 (never
    attempted) or 1-4, derived from the learner's own best_score on that
    topic's unit (see routers/progress.py's get_dashboard)."""

    topic: str
    topic_es: str
    level: int


class BookStub(BaseModel):
    """Catalog entry: free, static metadata for a library title. The actual
    story text is generated (and cached) on first read — see backend/library.py
    and HFClient.generate_book_content."""

    id: str
    title: str
    genre: str
    genre_label: str
    level: CEFRLevel
    blurb: str


class BookContent(BaseModel):
    id: str
    title: str
    genre_label: str
    level: CEFRLevel
    content: str


class AcademicLevel(StrEnum):
    """Self-paced study depth — explicitly NOT an accredited credential (see
    the disclaimer shown everywhere this appears in the UI). Named after the
    real-world credential each track's scope roughly mirrors, purely so
    learners have a sense of how much ground it covers."""

    ASSOCIATE = "ASSOCIATE"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"

    @property
    def label_es(self) -> str:
        return {
            AcademicLevel.ASSOCIATE: "Técnico (equivalente a Asociado)",
            AcademicLevel.BACHELOR: "Profesional (equivalente a Licenciatura)",
            AcademicLevel.MASTER: "Avanzado (equivalente a Maestría)",
        }[self]

    @property
    def course_count(self) -> int:
        return {AcademicLevel.ASSOCIATE: 12, AcademicLevel.BACHELOR: 24, AcademicLevel.MASTER: 10}[self]


class AcademicField(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    description: str
    tutor_name: str
    # A specialization builds on a base career instead of duplicating its
    # foundational courses — e.g. "Artificial Intelligence" specializing on
    # "computer-science". None for an ordinary, standalone field. See
    # backend/academy_library/build.py: a specialization's own build only
    # generates its extra advanced courses; the served curriculum then
    # prepends the base field's already-built courses ahead of them.
    base_field_id: str | None = None


class CourseStub(BaseModel):
    id: str
    order: int
    title: str
    description: str


class Curriculum(BaseModel):
    field_id: str
    field_name: str
    level: AcademicLevel
    level_label: str
    courses: list[CourseStub]


class CourseModule(BaseModel):
    title: str
    content: str


class CourseContent(BaseModel):
    id: str
    title: str
    modules: list[CourseModule]


class Assignment(BaseModel):
    """A real, gradeable piece of schoolwork for a course — a homework task,
    a written report, or a small project, the same kinds of work a normal
    school or university course would assign — as opposed to the optional,
    ungraded practice scenario (see get_practice_scenario)."""

    id: str
    type: str  # "tarea" | "informe" | "proyecto"
    title: str
    instructions: str
    submitted: bool = False
    response: str = ""
    feedback: str = ""
    grade: str = ""


class AcademyEnrollment(BaseModel):
    field_id: str
    field_name: str
    tutor_name: str
    icon: str
    category: str
    level: AcademicLevel
    level_label: str
    enrolled_at: str
    # The language course content (curriculum, readings, scenarios,
    # assignments) is generated in — independent of the learner's own
    # native_lang, so e.g. a Spanish speaker can study Computer Science in
    # English for extra immersion. Defaults to native_lang at enroll time.
    content_lang: str


class AcademyProgress(BaseModel):
    enrollment: AcademyEnrollment | None
    completed_course_ids: list[str] = Field(default_factory=list)
    total_courses: int = 0


class Recommendation(BaseModel):
    kind: str  # "book" | "song" | "podcast" | "show"
    title: str
    creator: str
    reason: str


class DashboardData(BaseModel):
    user_id: str
    xp: int
    streak_days: int
    gems: int
    streak_freezes: int
    level: CEFRLevel
    next_level: CEFRLevel | None
    due_reviews: int
    units_mastered_current_level: int
    units_total_current_level: int
    units_required_for_next_level: int
    daily_goal_minutes: int
    today_minutes: int
    mastery_by_level: list[LevelMastery]
    activity: list[ActivityDay]
    recent_lessons: list[RecentLesson]
    leaderboard: list[LeaderboardEntry]
    your_weekly_xp: int
    your_rank: int | None
    topic_mastery: list[TopicMastery]
