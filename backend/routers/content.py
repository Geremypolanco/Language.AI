"""Media generation endpoints: TTS audio, vocab-illustration images (free
Google Image Search first, AI generation as fallback — see image_search.py),
and short topic-explainer videos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth, image_search
from ..curriculum import build_conversation_system_prompt
from ..hf_client import hf_client
from ..models import CEFRLevel, Recommendation

# Gated behind "signed in" (any account, not a specific user_id) — video and
# speech-to-text still hit optional paid HF inference, so none of these
# should be reachable by anonymous traffic on a public deployment.
router = APIRouter(prefix="/api/content", tags=["content"], dependencies=[Depends(auth.require_session)])


class TTSRequest(BaseModel):
    text: str
    target_lang: str


@router.post("/tts")
async def text_to_speech(payload: TTSRequest) -> Response:
    audio = await hf_client.text_to_speech(payload.text, payload.target_lang)
    if audio is None:
        raise HTTPException(status_code=503, detail="Audio no disponible en este momento — inténtalo de nuevo")
    return Response(content=audio, media_type="audio/flac")


class ImageRequest(BaseModel):
    prompt: str


@router.post("/image")
async def generate_image(payload: ImageRequest) -> Response:
    # Real free photos first (cheaper and often clearer for a vocabulary
    # flashcard than an AI illustration) — falls straight through to the
    # existing AI generation when Google Image Search isn't configured.
    image = await image_search.search_image(payload.prompt)
    if image is None:
        image = await hf_client.generate_image(payload.prompt)
    if image is None:
        raise HTTPException(status_code=503, detail="Imagen no disponible en este momento — inténtalo de nuevo")
    return Response(content=image, media_type="image/jpeg")


class VideoRequest(BaseModel):
    prompt: str


@router.post("/video")
async def generate_video(payload: VideoRequest) -> Response:
    video = await hf_client.generate_video(payload.prompt)
    if video is None:
        raise HTTPException(status_code=503, detail="Video no disponible en este momento — inténtalo de nuevo más tarde")
    return Response(content=video, media_type="video/mp4")


@router.post("/stt")
async def speech_to_text(request: Request) -> dict:
    """Used by the speak_repeat pronunciation exercise: the client posts the raw
    recorded audio bytes and gets back a transcript to self-check against."""
    audio_bytes = await request.body()
    content_type = request.headers.get("content-type", "audio/webm")
    text = await hf_client.speech_to_text(audio_bytes, content_type)
    return {"text": text}


class TutorReplyRequest(BaseModel):
    target_lang: str
    native_lang: str
    level: CEFRLevel
    interests: list[str] = Field(default_factory=list)
    prompt: str
    user_answer: str


@router.post("/tutor-reply")
async def tutor_reply(payload: TutorReplyRequest) -> dict:
    """Gives the free_conversation_prompt exercise a real, short in-character
    tutor reply instead of a canned "Correct!"/"Not quite" banner — the same
    tutor persona used in Talk Live, so a lesson's free-response question
    feels like part of one ongoing conversation rather than a form field."""
    system_prompt = build_conversation_system_prompt(
        payload.target_lang, payload.native_lang, payload.level, payload.interests
    )
    history = [
        {"role": "assistant", "content": payload.prompt},
        {"role": "user", "content": payload.user_answer},
    ]
    reply = await hf_client.conversation_reply(system_prompt, history)
    return {"reply": reply}


class RecommendationsRequest(BaseModel):
    target_lang: str
    level: CEFRLevel
    interests: list[str] = Field(default_factory=list)


@router.post("/recommendations", response_model=list[Recommendation])
async def get_recommendations(payload: RecommendationsRequest) -> list[Recommendation]:
    """Suggests real books, songs, podcasts, and shows to reinforce learning
    outside the app's own lessons — the user's own request: "la plataforma
    debe de sugerir libros, canciones, y otras cosas que ayude a mejorar aún
    más el aprendizaje"."""
    items = await hf_client.generate_recommendations(payload.target_lang, payload.level.value, payload.interests)
    return [Recommendation(**item) for item in items]
