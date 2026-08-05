"""Shared types for the AI orchestration layer (backend/ai/) — see
AI_ARCHITECTURE.md for the full design this package implements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AITask(StrEnum):
    """Every AI capability this app performs, one entry per specialized
    router (backend/ai/routers/). Used to key backend/ai/registry.py's
    MODEL_REGISTRY, so each router's `active_chain` property always reflects
    the same source of truth documented there."""

    CHAT = "chat"                          # dialogue, content authoring
    EVALUATION = "evaluation"              # grading/judging a learner's own answer
    TRANSCRIPTION = "transcription"        # speech -> text
    SPEECH_SYNTHESIS = "speech_synthesis"  # text -> speech
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    EMBEDDING = "embedding"                # text -> vector, semantic search
    RERANKING = "reranking"                # reordering retrieved candidates by relevance


@dataclass(frozen=True)
class ModelSpec:
    """One entry in the model registry: a specific model this app can call
    for a given AITask, plus why it's here.

    `provider` is the actual transport — an HF Inference Providers model id,
    a Groq model name, a Pollinations model alias, ElevenLabs, or a locally
    -run engine like Piper — not every ModelSpec is a Hugging Face model,
    because a couple of tasks (chat, images) are deliberately routed to a
    faster/cheaper free-tier provider first, with a Hugging Face model as
    the documented fallback. See registry.py's module docstring for the
    reliability/cost reasoning behind that, proven in production before this
    orchestrator existed.

    `tier` is "primary" (tried first), "fallback" (tried when primary is
    unavailable/exhausted), or "specialist" (used only for a specific
    sub-case, e.g. persona voices, not the default path)."""

    model_id: str
    provider: str
    tier: str
    rationale: str
