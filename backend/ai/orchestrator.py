"""AIOrchestrator — the single entry point for every AI capability in this
app. Rather than each router/service/build script reaching into
hf_client.py directly for whatever call it happens to need, callers reach
for one of:

    ai_orchestrator.llm          — chat / dialogue / content authoring
    ai_orchestrator.speech       — text-to-speech (real-time + offline) and speech-to-text
    ai_orchestrator.vision       — image and video generation
    ai_orchestrator.embeddings   — semantic search / similarity ranking
    ai_orchestrator.evaluation   — grading a learner's own free-form work

See AI_ARCHITECTURE.md for the full design and backend/ai/registry.py for
which model each router actually calls today, and why. Every router here
still delegates the real network calls to hf_client (and, transitively,
piper_tts/image_search) — this layer is an organizational facade over
already production-proven reliability engineering (retries, circuit
breakers, the shared HF budget guard), not a reimplementation of it. See
each router module's docstring for the specifics of what it wraps."""

from __future__ import annotations

from ..hf_client import hf_client
from .routers.embeddings import EmbeddingRouter
from .routers.evaluation import EvaluationRouter
from .routers.llm import LLMRouter
from .routers.speech import SpeechRouter
from .routers.vision import VisionRouter


class AIOrchestrator:
    def __init__(self) -> None:
        self.llm = LLMRouter()
        self.speech = SpeechRouter()
        self.vision = VisionRouter()
        self.embeddings = EmbeddingRouter()
        self.evaluation = EvaluationRouter()

    async def aclose(self) -> None:
        await hf_client.aclose()


ai_orchestrator = AIOrchestrator()
