"""Thin wrapper around Hugging Face's Inference API for the four modalities
this app needs: chat/text generation (tutor + exercise authoring), text-to-image
(vocabulary flashcards), text-to-speech, and speech-to-text (conversation mode).

Falls back to a small local template generator when HF_TOKEN isn't configured,
so the app is fully runnable/demoable offline — but every call here is a real
HF request when a token is present (no mocked "success" responses).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import TYPE_CHECKING

import httpx

from .config import settings
from .curriculum import LessonRequest, build_exercise_generation_prompt, topic_es
from .models import Exercise, ExerciseType

if TYPE_CHECKING:
    from .models import AcademicField, AcademicLevel, BookStub

logger = logging.getLogger("lingua.hf_client")

# ISO 639-1 -> MMS-TTS ISO 639-3 code, covering every language offered in the
# frontend's picker (frontend/app.js LANGS). Exercise/chat generation is fully
# language-agnostic (any language the chat model knows works), so this map
# only controls which voice narrates audio; a target language missing here
# still teaches fully via text, it just falls back to an English voice.
_MMS_LANG_CODES = {
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "it": "ita",
    "pt": "por",
    "ja": "jpn",
    "ko": "kor",
    "zh": "cmn",
    "ru": "rus",
    "ar": "ara",
    "nl": "nld",
    "sv": "swe",
    "pl": "pol",
    "tr": "tur",
    "hi": "hin",
    "id": "ind",
    "vi": "vie",
    "th": "tha",
    "uk": "ukr",
    "el": "ell",
    "he": "heb",
    "cs": "ces",
    "ro": "ron",
    "hu": "hun",
    "fi": "fin",
    "da": "dan",
    "no": "nob",
    "bg": "bul",
    "sk": "slk",
    "hr": "hrv",
    "sr": "srp",
    "lt": "lit",
    "lv": "lav",
    "et": "est",
    "sl": "slv",
    "fa": "fas",
    "ur": "urd",
    "bn": "ben",
    "ta": "tam",
    "te": "tel",
    "mr": "mar",
    "gu": "guj",
    "pa": "pan",
    "ml": "mal",
    "kn": "kan",
    "ne": "nep",
    "si": "sin",
    "my": "mya",
    "km": "khm",
    "lo": "lao",
    "ms": "zlm",
    "tl": "tgl",
    "sw": "swh",
    "am": "amh",
    "so": "som",
    "ha": "hau",
    "yo": "yor",
    "ig": "ibo",
    "zu": "zul",
    "xh": "xho",
    "af": "afr",
    "is": "isl",
    "ga": "gle",
    "cy": "cym",
    "mt": "mlt",
    "eu": "eus",
    "ca": "cat",
    "gl": "glg",
    "az": "azj",
    "kk": "kaz",
    "uz": "uzn",
    "mn": "khk",
    "ka": "kat",
    "hy": "hye",
    "sq": "als",
    "mk": "mkd",
}


class HFClientError(RuntimeError):
    pass


class HFClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=settings.request_timeout_s)
        os.makedirs(settings.cache_dir, exist_ok=True)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.hf_token}"}

    def _cache_path(self, namespace: str, key: str, ext: str) -> str:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return os.path.join(settings.cache_dir, f"{namespace}-{digest}.{ext}")

    # ── Chat / text generation ──────────────────────────────────────────

    async def chat(self, messages: list[dict[str, str]], max_tokens: int = 700, temperature: float = 0.7) -> str:
        if not settings.hf_configured:
            raise HFClientError("HF_TOKEN not configured")
        resp = await self._http.post(
            settings.hf_chat_endpoint,
            headers=self._headers(),
            json={
                "model": settings.chat_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if resp.status_code != 200:
            raise HFClientError(f"HF chat HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def generate_exercises(
        self, req: LessonRequest, mix_override: list[ExerciseType] | None = None
    ) -> list[Exercise]:
        prompt = build_exercise_generation_prompt(req, mix_override)
        if settings.hf_configured:
            try:
                raw = await self.chat(
                    [
                        {"role": "system", "content": "You output only valid JSON, nothing else."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1500,
                )
                return _parse_exercises(raw)
            except Exception:
                logger.exception("HF exercise generation failed, using offline fallback content")
        return _fallback_exercises(req, mix_override)

    async def conversation_reply(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        if not settings.hf_configured:
            return (
                "(modo demo — configura HF_TOKEN para activar al tutor de IA real) "
                "¡Qué bien, cuéntame más!"
            )
        messages = [{"role": "system", "content": system_prompt}, *history]
        return await self.chat(messages, max_tokens=300, temperature=0.8)

    # ── Library (on-demand AI-generated books) ──────────────────────────

    async def generate_book_content(self, stub: "BookStub", target_lang: str, native_lang: str) -> str:
        """Generates (once) and caches the full text of a library book, keyed by
        (book id, target language) so the same title read in two different
        target languages gets two independently generated, cached copies."""
        from .library import build_book_generation_prompt

        cache_path = self._cache_path("book", f"{stub.id}:{target_lang}", "txt")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return f.read()

        if not settings.hf_configured:
            return (
                f"(Modo demo — configura HF_TOKEN para generar el libro completo con IA)\n\n"
                f'"{stub.title}" es una historia de {stub.genre_label.lower()} pensada para el nivel '
                f"{stub.level.value} en {target_lang}. Cuando actives tu clave de Hugging Face, esta "
                f"página mostrará el libro completo, generado especialmente para ti."
            )

        prompt = build_book_generation_prompt(stub, target_lang, native_lang)
        try:
            content = await self.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a language-learning story author. You write only in the "
                        "requested target language, at the requested CEFR difficulty, with no "
                        "explanations outside the story itself.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1400,
                temperature=0.85,
            )
        except Exception:
            logger.exception("HF book generation failed, using offline fallback content")
            return (
                f"(No se pudo generar el libro en este momento — inténtalo de nuevo en un momento)\n\n"
                f'"{stub.title}" — {stub.genre_label}, nivel {stub.level.value}.'
            )

        # Only successful HF generations are cached — a demo/error message
        # must never get stuck on disk and block real content once a token
        # is configured (same rule the image/TTS caches already follow).
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content

    # ── Academy (on-demand AI-generated accelerated study curricula) ────

    async def generate_curriculum(self, field: "AcademicField", level: "AcademicLevel", native_lang: str) -> list[dict]:
        """Generates (once) and caches the ordered course list for a
        (field, academic level) pair — analogous to generate_book_content,
        but for a curriculum outline instead of a story."""
        from .academy import build_curriculum_prompt

        cache_key = f"{field.id}:{level.value}:{native_lang}"
        cache_path = self._cache_path("curriculum", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

        if not settings.hf_configured:
            return _fallback_curriculum(field, level)

        prompt = build_curriculum_prompt(field, level.label_es, level.course_count, native_lang)
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1600,
                temperature=0.5,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            items = json.loads(cleaned)
            courses = [
                {"title": item.get("title", ""), "description": item.get("description", "")}
                for item in items
                if item.get("title")
            ]
        except Exception:
            logger.exception("HF curriculum generation failed, using offline fallback content")
            return _fallback_curriculum(field, level)

        # Only successful HF generations are cached — same rule as books: a
        # fallback must never get stuck on disk once a token is configured.
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(courses, f)
        return courses

    async def generate_course_content(
        self,
        field: "AcademicField",
        level: "AcademicLevel",
        course_id: str,
        course_title: str,
        course_description: str,
        native_lang: str,
    ) -> list[dict]:
        """Generates (once) and caches a course's module content."""
        from .academy import build_course_prompt

        cache_key = f"{course_id}:{native_lang}"
        cache_path = self._cache_path("course", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

        if not settings.hf_configured:
            return [
                {
                    "title": "Modo demo",
                    "content": (
                        f"(Modo demo — configura HF_TOKEN para generar el contenido completo del curso con IA)\n\n"
                        f'"{course_title}" — {course_description}\n\n'
                        f"Cuando actives tu clave de Hugging Face, este curso mostrará varios módulos de "
                        f"contenido completo, generados especialmente para tu carrera."
                    ),
                }
            ]

        prompt = build_course_prompt(field, level.label_es, course_title, course_description, native_lang)
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1800,
                temperature=0.6,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            items = json.loads(cleaned)
            modules = [
                {"title": item.get("title", ""), "content": item.get("content", "")}
                for item in items
                if item.get("content")
            ]
        except Exception:
            logger.exception("HF course generation failed, using offline fallback content")
            return [
                {
                    "title": "No se pudo generar el curso",
                    "content": "Inténtalo de nuevo en un momento.",
                }
            ]

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(modules, f)
        return modules

    # ── Recommendations (books, songs, and other media) ─────────────────

    async def generate_recommendations(
        self, target_lang: str, level: str, interests: list[str]
    ) -> list[dict]:
        if not settings.hf_configured:
            interest_note = f" relacionado con {interests[0]}" if interests else ""
            return [
                {
                    "kind": "book",
                    "title": f"Busca cuentos ilustrados para nivel {level}",
                    "creator": f"En {target_lang}",
                    "reason": f"Ideal para tu nivel{interest_note} — configura HF_TOKEN para recomendaciones con IA.",
                },
                {
                    "kind": "song",
                    "title": f"Explora listas de música popular en {target_lang}",
                    "creator": "Playlists para principiantes",
                    "reason": "Escuchar música es una forma natural de entrenar el oído.",
                },
                {
                    "kind": "podcast",
                    "title": f"Busca podcasts para aprender {target_lang}",
                    "creator": "Episodios cortos y lentos",
                    "reason": "Los podcasts para estudiantes narran más despacio y repiten vocabulario clave.",
                },
            ]

        interests_note = f" The learner is interested in: {', '.join(interests)}." if interests else ""
        prompt = (
            f"Suggest 6 real, well-known books, songs, podcasts, or shows that would help someone "
            f"learn {target_lang} at CEFR level {level}.{interests_note} Only suggest items you are "
            f"confident actually exist — do not invent titles or creators. "
            f'Respond with ONLY a JSON array, no other text, each item shaped like: '
            f'{{"kind": "book|song|podcast|show", "title": "...", "creator": "author or artist name", '
            f'"reason": "one short sentence on why it fits this level/interest"}}'
        )
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=900,
                temperature=0.6,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            items = json.loads(cleaned)
            return [
                {
                    "kind": item.get("kind", "book"),
                    "title": item.get("title", ""),
                    "creator": item.get("creator", ""),
                    "reason": item.get("reason", ""),
                }
                for item in items
            ]
        except Exception:
            logger.exception("HF recommendations generation failed, using offline fallback content")
            return [
                {
                    "kind": "book",
                    "title": f"Busca cuentos ilustrados para nivel {level}",
                    "creator": f"En {target_lang}",
                    "reason": "No se pudieron generar recomendaciones personalizadas en este momento.",
                }
            ]

    # ── Text-to-image (vocab flashcards) ────────────────────────────────

    async def generate_image(self, prompt: str) -> bytes | None:
        cache_path = self._cache_path("img", prompt, "jpg")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read()
        if not settings.hf_configured:
            return None
        try:
            resp = await self._http.post(
                f"{settings.hf_models_endpoint}/{settings.image_model}",
                headers=self._headers(),
                json={"inputs": prompt},
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                return resp.content
            logger.warning("HF image generation HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("HF image generation failed")
        return None

    # ── Text-to-speech ──────────────────────────────────────────────────

    async def text_to_speech(self, text: str, target_lang: str) -> bytes | None:
        lang_code = _MMS_LANG_CODES.get(target_lang.lower()[:2], "eng")
        model = f"{settings.tts_model_prefix}-{lang_code}"
        cache_path = self._cache_path("tts", f"{model}:{text}", "flac")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read()
        if not settings.hf_configured:
            return None
        try:
            resp = await self._http.post(
                f"{settings.hf_models_endpoint}/{model}",
                headers=self._headers(),
                json={"inputs": text},
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                return resp.content
            logger.warning("HF TTS HTTP %s (%s): %s", resp.status_code, model, resp.text[:200])
        except Exception:
            logger.exception("HF TTS failed")
        return None

    # ── Speech-to-text ───────────────────────────────────────────────────

    async def speech_to_text(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
        if not settings.hf_configured:
            return ""
        try:
            resp = await self._http.post(
                f"{settings.hf_models_endpoint}/{settings.stt_model}",
                headers={**self._headers(), "Content-Type": content_type},
                content=audio_bytes,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("text", "").strip()
            logger.warning("HF STT HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("HF STT failed")
        return ""


def _parse_exercises(raw: str) -> list[Exercise]:
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    items = json.loads(cleaned)
    exercises = []
    for i, item in enumerate(items):
        exercises.append(
            Exercise(
                id=f"ex-{i}-{item.get('vocab_key', i)}",
                type=ExerciseType(item["type"]),
                prompt=item.get("prompt", ""),
                target_text=item.get("target_text", ""),
                native_text=item.get("native_text", ""),
                options=item.get("options", []) or [],
                correct_answer=item.get("correct_answer", item.get("target_text", "")),
                image_prompt=item.get("image_prompt", ""),
                audio_text=item.get("audio_text", item.get("target_text", "")),
                vocab_key=item.get("vocab_key", f"item-{i}"),
            )
        )
    return exercises


def _fallback_exercises(req: LessonRequest, mix_override: list[ExerciseType] | None = None) -> list[Exercise]:
    """Deterministic, network-free content so the app works with no HF_TOKEN
    (useful for local dev/demo/tests). Clearly lower quality than the real
    LLM-generated, personalized content."""
    from .curriculum import exercise_mix_for

    mix = mix_override if mix_override is not None else exercise_mix_for(req.unit.level)
    topic = topic_es(req.unit.topic)
    exercises = []
    for i, ex_type in enumerate(mix):
        word = f"{req.unit.topic.split()[0].lower()}_{i}"
        target = f"[{req.target_lang}] {topic}, ejemplo {i + 1}"
        native = f"[{req.native_lang}] {topic}, ejemplo {i + 1}"
        exercises.append(
            Exercise(
                id=f"ex-{i}-{word}",
                type=ex_type,
                prompt=f"Practica: {topic}",
                target_text=target,
                native_text=native if req.unit.level.uses_translation else "",
                options=[target, f"{target} (opción A)", f"{target} (opción B)"]
                if ex_type in (ExerciseType.MULTIPLE_CHOICE, ExerciseType.IMAGE_MATCH)
                else [],
                correct_answer=target,
                image_prompt=f"a simple, clear illustration of {req.unit.topic}, item {i + 1}",
                audio_text=target,
                vocab_key=f"{req.unit.id}.{word}",
            )
        )
    return exercises


def _fallback_curriculum(field: "AcademicField", level: "AcademicLevel") -> list[dict]:
    """Deterministic, network-free course list so the academy works with no
    HF_TOKEN — same role as _fallback_exercises for lessons."""
    return [
        {
            "title": f"{field.name} — módulo {i + 1}",
            "description": "(Modo demo — configura HF_TOKEN para un plan de estudios completo con IA)",
        }
        for i in range(level.course_count)
    ]


hf_client = HFClient()
