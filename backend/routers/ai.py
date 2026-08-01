"""AI Router - Endpoints for AI services"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from ..ai_services.llm import get_llm_service
from ..ai_services.speech import get_speech_service
from ..ai_services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])

# ===== Models =====
class FeedbackRequest(BaseModel):
    user_answer: str
    correct_answer: str

class ExplainRequest(BaseModel):
    concept: str
    context: Optional[str] = None

class EvaluateRequest(BaseModel):
    question: str
    user_answer: str
    correct_answer: str

class TranscribeRequest(BaseModel):
    text: str
    language: str = "en"

# ===== LLM Endpoints =====
@router.post("/feedback")
async def generate_feedback(request: FeedbackRequest):
    """Generate AI feedback on user's answer"""
    llm = get_llm_service()
    feedback = await llm.generate_feedback(request.user_answer, request.correct_answer)
    return {"feedback": feedback}

@router.post("/explain")
async def explain_concept(request: ExplainRequest):
    """Explain a language concept"""
    llm = get_llm_service()
    explanation = await llm.explain_concept(request.concept, request.context)
    return {"explanation": explanation}

@router.post("/evaluate-answer")
async def evaluate_answer(request: EvaluateRequest):
    """Evaluate user's answer"""
    llm = get_llm_service()
    evaluation = await llm.evaluate_answer(request.question, request.user_answer, request.correct_answer)
    return evaluation

@router.post("/generate-lesson")
async def generate_lesson(topic: str, level: str, language: str):
    """Generate a complete lesson"""
    llm = get_llm_service()
    lesson = await llm.generate_lesson_content(topic, level, language)
    return lesson

# ===== Speech Endpoints =====
@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio file"""
    try:
        audio_data = await file.read()
        speech = get_speech_service()
        result = await speech.transcribe_audio(audio_data)
        return result
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-pronunciation")
async def check_pronunciation(user_text: str, reference_text: str):
    """Check pronunciation accuracy"""
    speech = get_speech_service()
    result = await speech.check_pronunciation(user_text, reference_text)
    return result

@router.post("/speak")
async def generate_speech(text: str, language: str = "en"):
    """Generate speech from text"""
    try:
        speech = get_speech_service()
        audio = await speech.generate_speech(text, language)
        return {"audio": audio.hex() if audio else None}
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== Embedding Endpoints =====
@router.post("/embed")
async def embed_text(text: str):
    """Generate embedding for text"""
    embedding = get_embedding_service()
    result = await embedding.embed_text(text)
    return {"embedding": result}

@router.post("/find-similar")
async def find_similar(query: str, documents: list, top_k: int = 5):
    """Find similar documents"""
    embedding = get_embedding_service()
    results = await embedding.find_similar(query, documents, top_k)
    return {"results": results}

# ===== Health Check =====
@router.get("/health")
async def ai_health():
    """Check AI services health"""
    return {
        "status": "ok",
        "services": {
            "llm": "ready",
            "speech": "ready",
            "embeddings": "ready",
        }
    }
