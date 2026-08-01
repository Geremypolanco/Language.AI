"""Media generation endpoints: TTS audio, vocab-illustration images (free
Google Image Search first, AI generation as fallback — see image_search.py),
and short topic-explainer videos."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth, image_search, youtube_search
from ..curriculum import build_conversation_system_prompt
from ..hf_client import hf_client
from ..models import CEFRLevel, Recommendation
from .users import get_user_by_id_or_404

# Gated behind "signed in" (any account, not a specific user_id) — video and
# speech-to-text still hit optional paid HF inference, so none of these
# should be reachable by anonymous traffic on a public deployment.
router = APIRouter(prefix="/api/content", tags=["content"], dependencies=[Depends(auth.require_session)])


class TTSRequest(BaseModel):
    text: str
    target_lang: str


@router.post("/tts")
async def text_to_speech(payload: TTSRequest) -> Response:
    result = await hf_client.text_to_speech(payload.text, payload.target_lang)
    if result is None:
        raise HTTPException(status_code=503, detail="Audio no disponible en este momento — inténtalo de nuevo")
    audio, media_type = result
    return Response(content=audio, media_type=media_type)


class ImageRequest(BaseModel):
    prompt: str
    # Exercise illustrations (see ExercisePlayer.tsx's image_match rendering)
    # send crafted, specific AI-image-generation descriptions (e.g. "two
    # people shaking hands, simple flat illustration"), not natural search
    # queries. Wikimedia Commons' search is a blind top-1 keyword match over
    # its own file titles/descriptions with no relevance/semantic check —
    # confirmed live: an exercise about someone waving hello returned an
    # unrelated ocean-waves photo, because "wave" the gesture and "wave" the
    # water feature collide in a plain keyword index, and Commons' media
    # library is dominated by the latter. AI generation directly renders
    # what was actually asked for instead of hoping a keyword search
    # happens to agree, so exercise callers skip straight to it.
    skip_photo_search: bool = False


@router.post("/image")
async def generate_image(payload: ImageRequest) -> Response:
    image = None
    if not payload.skip_photo_search:
        # Real free photos first (cheaper and often clearer for a
        # general vocabulary flashcard than an AI illustration): Google
        # Image Search if configured (best relevance), then Wikimedia
        # Commons (needs no setup at all, so every install gets real
        # photos even without configuring Google CSE).
        image = await image_search.search_image(payload.prompt)
        if image is None:
            image = await image_search.search_wikimedia_commons(payload.prompt)
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


class YoutubeSearchRequest(BaseModel):
    query: str
    limit: int = 1


@router.post("/youtube-search")
async def search_youtube(payload: YoutubeSearchRequest) -> list[dict[str, str]]:
    """Searches real YouTube videos based on the context."""
    return await youtube_search.search_youtube_videos(payload.query, payload.limit)


class ImageGalleryRequest(BaseModel):
    query: str
    limit: int = 4


@router.post("/image-gallery")
async def get_image_gallery(payload: ImageGalleryRequest) -> list[str]:
    """Returns same-origin URLs for a real image gallery (Google Image
    Search / Wikimedia Commons — the same sources /image already uses, via
    image_search.search_images), each served by /image-gallery-item below.
    Same-origin because the CSP's img-src is 'self' (plus a couple of
    specific exceptions for other features) — this endpoint used to return
    raw image.pollinations.ai URLs straight to the client, which wasn't
    real "Google Images" at all, just 4 near-identical AI-generated
    illustrations of the same prompt."""
    limit = max(1, min(payload.limit, 10))
    return [
        f"/api/content/image-gallery-item?query={quote(payload.query)}&limit={limit}&index={i}"
        for i in range(limit)
    ]


@router.get("/image-gallery-item")
async def get_gallery_item(query: str, index: int = 0, limit: int = 4) -> Response:
    images = await image_search.search_images(query, count=limit)
    if index < len(images):
        return Response(content=images[index], media_type="image/jpeg")
    # Fewer real results than gallery slots requested — fill the rest with
    # AI generation rather than leaving a broken <img>.
    image = await hf_client.generate_image(query)
    if image is None:
        raise HTTPException(status_code=503, detail="Imagen no disponible en este momento — inténtalo de nuevo")
    return Response(content=image, media_type="image/jpeg")


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
    outside the app's own lessons."""
    items = await hf_client.generate_recommendations(payload.target_lang, payload.level.value, payload.interests)
    return [Recommendation(**item) for item in items]


class ExplainRequest(BaseModel):
    text: str
    context: str = ""
    target_lang: str = "en"
    native_lang: str = "es"


@router.get("/news")
async def get_daily_news(request: Request) -> dict:
    """Generates personalized news based on user interests using RAG."""
    session = auth.get_session(request)
    user = get_user_by_id_or_404(session["user_id"])
    
    interests = ",".join(user.interests) if user.interests else "general news"
    prompt = f"""Generate 3 short, elite news summaries for today in {user.target_lang} (with translations in {user.native_lang}).
Topics: {interests}.
Level: {user.level.value}.
Format: Return ONLY a JSON array of objects: [{{"title": "...", "content": "...", "translation": "..."}}]"""
    
    try:
        import json
        import re
        news_raw = await hf_client.chat([{"role": "user", "content": prompt}], max_tokens=800)
        cleaned = re.sub(r"^```(json)?|```$", "", news_raw.strip(), flags=re.MULTILINE).strip()
        news = json.loads(cleaned)
        return {"news": news}
    except Exception:
        # hf_client.chat can itself raise (all providers down, or disabled
        # in tests) — that used to happen outside this try/except, before
        # it only wrapped the JSON parsing, so it 500'd instead of using
        # this endpoint's own intended fallback below.
        return {"news": [{"title": "News Unavailable", "content": "The AI news anchor is sleeping. Try again later.", "translation": ""}]}


@router.post("/explain")
async def explain_text(payload: ExplainRequest) -> dict:
    """The 'Magic Lens' feature: provides an elite AI explanation for any word or phrase."""
    prompt = f"""Explain the word or phrase "{payload.text}" in the context of: "{payload.context}".
The learner is studying {payload.target_lang} and their native language is {payload.native_lang}.
Provide:
1. A clear, elite explanation of the meaning and usage.
2. 2-3 natural example sentences.
3. A brief grammatical note if applicable.
Respond in {payload.native_lang} with a professional, encouraging tone."""
    
    explanation = await hf_client.chat([{"role": "user", "content": prompt}], max_tokens=500)
    return {"explanation": explanation}
