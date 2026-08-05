"""The AI orchestration layer — see AI_ARCHITECTURE.md for the design and
backend/ai/orchestrator.py for the entry point most callers want."""

from .orchestrator import AIOrchestrator, ai_orchestrator

__all__ = ["AIOrchestrator", "ai_orchestrator"]
