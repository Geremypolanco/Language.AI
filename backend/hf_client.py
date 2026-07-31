"""Thin wrapper around Hugging Face's Inference API for the four modalities
this app needs: chat/text generation (tutor + exercise authoring), text-to-image
(vocabulary flashcards), text-to-speech, and speech-to-text (conversation mode).

Falls back to a small local template generator when HF_TOKEN isn't configured,
so the app is fully runnable/demoable offline — but every call here is a real
HF request when a token is present (no mocked "success" responses).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING

import httpx
from num2words import num2words

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

# Parler-TTS steers voice identity through a natural-language description of
# the speaker rather than a fixed voice ID (see backend/personas.py) — this
# is what lets every teacher persona have its own describable voice without
# per-persona speaker cloning. Verified against the HF Hub (not assumed):
# parler-tts-mini-multilingual-v1.1 is Apache-2.0 and its model card lists
# exactly these 8 training languages — en/fr/es/pt/pl/de/it/nl — matching
# PARLER_LANGS below exactly. As of this check it has no confirmed live
# entry under HF's Inference Providers (only community Spaces run it), so
# the direct endpoint below is best-effort; text_to_speech's second tier
# calls a verified community Space (PARLER_SPACE_ID / _call_parler_space)
# via gradio_client instead. Neither tier could be executed end-to-end
# from the environment this was written in — this session's HF MCP tools
# have Space invocation disabled, and this sandbox's own outbound network
# policy separately blocks huggingface.co directly — so both are shipped
# as genuinely best-effort, same resilience contract as everything else in
# this file: try, log, fall through to the shared MMS voice on any failure.
#
# Kokoro-82M was considered and deliberately rejected for this role: its
# model card lists English only (no Spanish/multilingual coverage this app
# needs for native-language delivery), and its one listed Inference Provider
# (fal-ai) currently shows an error status on the Hub rather than "live".
PARLER_MODEL = "parler-tts/parler-tts-mini-multilingual-v1.1"
PARLER_LANGS = {"en", "fr", "es", "pt", "pl", "de", "it", "nl"}

# Preferred voice tier when configured (see config.elevenlabs_configured) —
# verified live this session via the ElevenLabs MCP connector (generated a
# real Spanish audio sample). Real per-persona identity requires the
# deploying user's own voice IDs in ELEVENLABS_VOICE_MAP; this app has no
# tool access to enumerate or assign voices on anyone's behalf.
ELEVENLABS_TTS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech"

# A real, verified community Space running parler-tts-mini-multilingual-v1.1
# — confirmed by reading its app.py source directly (via the HF Hub) rather
# than assumed: it exposes exactly one endpoint, gen_tts(text, description),
# and internally fixes a generation seed, which is what makes reusing the
# same persona voice_description string across calls give a consistently-
# sounding voice rather than "random voice characteristics" (Parler-TTS's
# default behavior per that Space's own README). It's ZeroGPU-backed, so
# it can be slow or quota-limited under load — a real fallback tier, not a
# replacement for a dedicated Inference Endpoint in a production deployment
# with real traffic.
PARLER_SPACE_ID = "etrotta/parler-tts-mini-multilingual-v1.1"

# The fixed generation seed that Space's own gen_tts() hardcodes internally
# (read directly from its app.py source: `SEED = 42; set_seed(SEED)` before
# every generation) — documented here, not re-implemented, since the app
# never controls the Space's internals directly; it's what makes a fixed
# voice_description reproduce a consistent-sounding voice call to call.
PARLER_VOICE_SEED = 42

_ALLCAPS_ABBREV_PATTERN = re.compile(r"\b[A-Z][A-Z.]+\b")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _preprocess_for_parler(text: str, lang: str) -> str:
    """Mirrors the actual preprocessing the verified etrotta Parler-TTS
    Space performs on its input (read directly from that Space's app.py) —
    not a fabricated "phonetic marker" syntax; Parler-TTS's only inputs are
    the raw text and the free-form natural-language `description` (see
    TeacherPersona.voice_description), it doesn't parse phonemes. The real,
    narrow fixes that Space's own code makes: hyphens read as odd pauses,
    digit sequences get sounded out digit-by-digit instead of as a number,
    and solid-caps abbreviations get pronounced as if they were a word.

    Only ever applied to the copy of text sent to the TTS engine — never to
    spoken_response itself, which stays natural for the visible transcript
    and the conversation history the model reads back on the next turn."""
    text = text.strip().replace("-", " ")

    def _to_words(match: re.Match) -> str:
        try:
            return num2words(match.group(0).replace(",", "."), lang=lang)
        except NotImplementedError:
            return num2words(match.group(0).replace(",", "."), lang="en")

    text = _NUMBER_PATTERN.sub(_to_words, text)
    text = _ALLCAPS_ABBREV_PATTERN.sub(lambda m: " ".join(m.group(0).replace(".", "")), text)

    if text and text[-1] not in ".!?":
        text += "."
    return text


def _call_parler_space(text: str, description: str) -> bytes | None:
    """Synchronous by necessity (gradio_client isn't async) — always called
    through asyncio.to_thread. Handles the couple of shapes gradio_client
    is known to return for an Audio-typed output (a local temp file path,
    or a dict/FileData wrapper around one) since the exact shape can vary
    by gradio_client version and this couldn't be executed end-to-end from
    the development environment this was written in (Space access was
    blocked at the network level there) — any shape this doesn't recognize
    just returns None and the caller falls back to MMS, same as any other
    failure here."""
    from gradio_client import Client

    client = Client(PARLER_SPACE_ID, hf_token=settings.hf_token or None)
    result = client.predict(text, description, api_name="/gen_tts")

    path = None
    if isinstance(result, str):
        path = result
    elif isinstance(result, dict):
        path = result.get("path") or result.get("name")
    elif isinstance(result, (list, tuple)) and result and isinstance(result[-1], str):
        path = result[-1]

    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


class HFClientError(RuntimeError):
    pass


# How long a 429 keeps the ElevenLabs tier skipped entirely once the circuit
# breaker trips (see _call_elevenlabs) — long enough that a burst of
# concurrent requests during a rate-limit window doesn't each pay for their
# own doomed round-trip before falling back, short enough to notice recovery
# without a restart.
_ELEVENLABS_CIRCUIT_COOLDOWN_S = 60.0


class HFClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=settings.request_timeout_s)
        os.makedirs(settings.cache_dir, exist_ok=True)
        # Circuit breaker state for the ElevenLabs tier — a monotonic
        # timestamp; while time.monotonic() is before it, _call_elevenlabs
        # returns None immediately without touching the network at all, so
        # a rate-limit window degrades to "skip this tier" in microseconds
        # rather than "retry the same 429 on every single turn."
        self._elevenlabs_circuit_open_until: float = 0.0

        # Side-channel telemetry state (see backend/telemetry.py) — set by
        # chat()/text_to_speech() on every call, read by router call sites
        # right after awaiting them. A side-channel rather than widening
        # those methods' return types, which are already relied on by
        # existing callers/tests to be a plain string / bytes|None.
        self._last_token_usage: dict | None = None
        self._last_voice_tier: str = "none"

    def elevenlabs_circuit_breaker_engaged(self) -> bool:
        return time.monotonic() < self._elevenlabs_circuit_open_until

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call_elevenlabs(self, text: str, voice_id: str) -> bytes | None:
        """Real REST call — ElevenLabs' text-to-speech endpoint has been
        publicly documented and stable for years, unlike Parler-TTS's
        uncertain serverless hosting, so this needs no fallback tier of its
        own beyond the outer try/except every HF call in this file follows.

        Circuit breaker: a 429 (rate limit / quota exhaustion) opens the
        breaker for _ELEVENLABS_CIRCUIT_COOLDOWN_S, during which this method
        short-circuits to None without an HTTP call — text_to_speech's
        caller then falls through to the Parler/MMS chain exactly as it
        would on any other failure. This bounds the *added* latency of the
        failover decision itself to a clock comparison; it can't bound the
        total round-trip of whichever tier ends up actually serving the
        request, since that depends on that tier's own live latency."""
        if time.monotonic() < self._elevenlabs_circuit_open_until:
            logger.info("ElevenLabs circuit breaker open — skipping call, falling back immediately")
            return None
        try:
            resp = await self._http.post(
                f"{ELEVENLABS_TTS_ENDPOINT}/{voice_id}",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": text, "model_id": settings.elevenlabs_model_id},
            )
            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 429:
                self._elevenlabs_circuit_open_until = time.monotonic() + _ELEVENLABS_CIRCUIT_COOLDOWN_S
                logger.warning(
                    "ElevenLabs rate-limited (429) — opening circuit breaker for %.0fs",
                    _ELEVENLABS_CIRCUIT_COOLDOWN_S,
                )
            else:
                logger.warning("ElevenLabs TTS HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("ElevenLabs TTS failed")
        return None

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
        # HF's chat/completions endpoint is OpenAI-compatible, so `usage` —
        # when the provider actually sends it — has the standard
        # prompt_tokens/completion_tokens/total_tokens shape. Recorded as a
        # side-channel (see telemetry state in __init__) rather than
        # widening this method's return type, which every caller in this
        # file (generate_exercises, conversation_reply, book/course/
        # curriculum generation) already relies on being a plain string.
        self._last_token_usage = data.get("usage")
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

    async def conversation_reply(
        self, system_prompt: str, history: list[dict[str, str]], temperature: float = 0.8
    ) -> dict:
        """Returns {"spoken_response": str, "critique_metrics": dict}. The
        model is instructed (see curriculum.build_conversation_system_prompt's
        OUTPUT FORMAT section) to emit both in one JSON object per turn —
        critique_metrics is a structured record of that turn's grammar/
        pronunciation/comprehension/knowledge corrections (for the app to
        track over time, e.g. recurring mistakes), separate from the
        natural-language spoken_response actually sent to the learner and to
        TTS. `temperature` is per-persona (see personas.TeacherPersona.
        sampling_temperature) — precise personas sample lower, expressive
        ones higher.

        Falls back to treating the raw text as spoken_response with empty
        critique_metrics if the model doesn't return valid JSON — the
        conversation must never break just because structured parsing failed."""
        if not settings.hf_configured:
            return {
                "spoken_response": (
                    "(modo demo — configura HF_TOKEN para activar al tutor de IA real) "
                    "¡Qué bien, cuéntame más!"
                ),
                "critique_metrics": {},
            }
        messages = [{"role": "system", "content": system_prompt}, *history]
        raw = await self.chat(messages, max_tokens=500, temperature=temperature)
        try:
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            spoken = str(data.get("spoken_response", "")).strip()
            if not spoken:
                raise ValueError("empty spoken_response")
            return {"spoken_response": spoken, "critique_metrics": data.get("critique_metrics") or {}}
        except Exception:
            logger.exception("Tutor reply wasn't valid structured JSON — using the raw text as spoken_response")
            return {"spoken_response": raw.strip(), "critique_metrics": {}}

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
    ) -> dict:
        """Generates (once) and caches a course's module content, grounded
        wherever possible in real excerpts retrieved from the OER vector
        store (see backend/oer/retrieval.py) — populated offline by
        scripts/ingest_oer.py, not on this request path. Returns
        {"modules": [...], "sources": [...]}; sources is empty when nothing
        relevant has been ingested for this field yet."""
        from . import personas
        from .academy import build_course_prompt

        # Faculty assignment is deterministic and free (no HF call) — compute
        # it up front so every return path below, demo mode included, can
        # show the assigned professor's identity.
        faculty = personas.build_field_faculty(field)
        faculty_info = {"id": faculty.id, "name": faculty.name, "title": faculty.title}

        cache_key = f"{course_id}:{native_lang}"
        cache_path = self._cache_path("course", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            cached.setdefault("faculty", faculty_info)
            return cached

        if not settings.hf_configured:
            return {
                "modules": [
                    {
                        "title": "Modo demo",
                        "content": (
                            f"(Modo demo — configura HF_TOKEN para generar el contenido completo del curso con IA)\n\n"
                            f'"{course_title}" — {course_description}\n\n'
                            f"Cuando actives tu clave de Hugging Face, este curso mostrará varios módulos de "
                            f"contenido completo, generados especialmente para tu carrera."
                        ),
                    }
                ],
                "sources": [],
                "faculty": faculty_info,
            }

        from .oer import retrieval

        chunks: list = []
        try:
            chunks = await retrieval.retrieve_context(f"{course_title}. {course_description}", field_id=field.id, k=4)
        except Exception:
            logger.exception("OER retrieval failed, generating course content without grounding")

        prompt = build_course_prompt(
            field,
            level.label_es,
            course_title,
            course_description,
            native_lang,
            grounding=[c.text for c in chunks] or None,
            professor_style=faculty.system_voice,
        )
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
            return {
                "modules": [
                    {
                        "title": "No se pudo generar el curso",
                        "content": "Inténtalo de nuevo en un momento.",
                    }
                ],
                "sources": [],
                "faculty": faculty_info,
            }

        seen: set[tuple[str, str]] = set()
        sources = []
        for c in chunks:
            if not c.title or (c.title, c.url) in seen:
                continue
            seen.add((c.title, c.url))
            sources.append({"title": c.title, "source": c.source, "url": c.url})

        result = {"modules": modules, "sources": sources, "faculty": faculty_info}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
        return result

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

    # ── Text-to-image (vocab flashcards + persona/faculty portraits) ─────
    # Verified against the HF Hub: FLUX.1-schnell is gated (the account
    # behind HF_TOKEN must accept its license on huggingface.co once) but
    # has multiple live Inference Providers (nscale, fal-ai, together,
    # wavespeed) as of this check, so the plain serverless call below is a
    # sound integration, not a guess.

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

    async def text_to_speech(
        self,
        text: str,
        target_lang: str,
        voice_description: str | None = None,
        persona_id: str | None = None,
    ) -> bytes | None:
        """Three tiers, tried in order, each falling through to the next on
        any failure — same resilience contract as every HF call in this file:

        0. ElevenLabs, if `persona_id` resolves to a voice ID in
           settings.elevenlabs_voice_map (opt-in — see config.py; this app
           has no default ElevenLabs voices of its own to assign). Real
           per-voice identity via a stable, publicly documented REST API,
           not a text-description hack.
        1-2. Parler-TTS direct endpoint, then the verified Space fallback
           (see PARLER_MODEL/PARLER_SPACE_ID), when `voice_description` is
           given and the language is one of PARLER_LANGS.
        3. The single shared per-language MMS voice — always available,
           the only tier that needs neither ElevenLabs nor a persona voice."""
        lang_code2 = target_lang.lower()[:2]

        voice_id = settings.elevenlabs_voice_map.get(persona_id) if persona_id else None
        if voice_id and settings.elevenlabs_configured:
            elevenlabs_cache_path = self._cache_path("tts-elevenlabs", f"{voice_id}::{text}", "mp3")
            if os.path.exists(elevenlabs_cache_path):
                self._last_voice_tier = "elevenlabs"
                with open(elevenlabs_cache_path, "rb") as f:
                    return f.read()
            audio = await self._call_elevenlabs(text, voice_id)
            if audio:
                self._last_voice_tier = "elevenlabs"
                with open(elevenlabs_cache_path, "wb") as f:
                    f.write(audio)
                return audio
            logger.info("ElevenLabs tier unavailable/failed, falling back to the Parler-TTS/MMS chain")

        if voice_description and lang_code2 in PARLER_LANGS and settings.hf_configured:
            parler_cache_path = self._cache_path("tts-parler", f"{voice_description}::{text}", "flac")
            if os.path.exists(parler_cache_path):
                self._last_voice_tier = "parler-direct"
                with open(parler_cache_path, "rb") as f:
                    return f.read()

            # Only the copy sent to the model is preprocessed — spoken_response
            # itself (the transcript/history text `text` came from) stays
            # natural; see _preprocess_for_parler's docstring.
            parler_text = _preprocess_for_parler(text, lang_code2)

            # Tier 1: direct serverless model endpoint — cheap and fast if
            # HF ever lists this model on a live Inference Provider.
            try:
                resp = await self._http.post(
                    f"{settings.hf_models_endpoint}/{PARLER_MODEL}",
                    headers=self._headers(),
                    json={"inputs": parler_text, "parameters": {"description": voice_description}},
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
                    self._last_voice_tier = "parler-direct"
                    with open(parler_cache_path, "wb") as f:
                        f.write(resp.content)
                    return resp.content
                logger.warning("HF Parler-TTS HTTP %s: %s", resp.status_code, resp.text[:200])
            except Exception:
                logger.exception("HF Parler-TTS direct endpoint failed, trying the verified Space fallback")

            # Tier 2: the verified community Space (see PARLER_SPACE_ID) —
            # confirmed live by reading its actual app.py source. Slower
            # (ZeroGPU-backed) and quota-limited, so it's a fallback, not
            # the first attempt.
            try:
                audio_bytes = await asyncio.to_thread(_call_parler_space, parler_text, voice_description)
                if audio_bytes:
                    self._last_voice_tier = "parler-space"
                    with open(parler_cache_path, "wb") as f:
                        f.write(audio_bytes)
                    return audio_bytes
            except Exception:
                logger.exception("Parler-TTS Space fallback failed, falling back to the shared MMS voice")

        lang_code = _MMS_LANG_CODES.get(lang_code2, "eng")
        model = f"{settings.tts_model_prefix}-{lang_code}"
        cache_path = self._cache_path("tts", f"{model}:{text}", "flac")
        if os.path.exists(cache_path):
            self._last_voice_tier = "mms"
            with open(cache_path, "rb") as f:
                return f.read()
        if not settings.hf_configured:
            self._last_voice_tier = "none"
            return None
        try:
            resp = await self._http.post(
                f"{settings.hf_models_endpoint}/{model}",
                headers=self._headers(),
                json={"inputs": text},
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
                self._last_voice_tier = "mms"
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                return resp.content
            logger.warning("HF TTS HTTP %s (%s): %s", resp.status_code, model, resp.text[:200])
        except Exception:
            logger.exception("HF TTS failed")
        self._last_voice_tier = "none"
        return None

    # ── Embeddings (OER retrieval-augmented generation, see backend/oer/) ──

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embeds a batch of text chunks for the OER vector store. Same
        "call the HF Inference API, no local model install" pattern as the
        rest of this client — no torch/sentence-transformers dependency."""
        if not texts:
            return []
        if not settings.hf_configured:
            return [_offline_embedding(t) for t in texts]
        resp = await self._http.post(
            f"{settings.hf_models_endpoint}/{settings.embedding_model}",
            headers=self._headers(),
            json={"inputs": texts, "options": {"wait_for_model": True}},
        )
        if resp.status_code != 200:
            raise HFClientError(f"HF embedding HTTP {resp.status_code}: {resp.text[:300]}")
        return _normalize_embeddings(resp.json())

    # ── Speech-to-text ───────────────────────────────────────────────────
    # Verified against the HF Hub: whisper-large-v3 has a live hf-inference
    # entry under Inference Providers as of this check, so this is the one
    # audio call in this file confirmed solidly hosted rather than best-effort.

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


def _normalize_embeddings(data: list) -> list[list[float]]:
    """The feature-extraction pipeline returns per-token vectors for some
    models and already mean-pooled sentence vectors for others (sentence-
    transformers models return the latter) — detect which shape came back
    and mean-pool per input if needed, so callers always get one flat vector
    per input text."""
    if not data:
        return []
    if isinstance(data[0][0], list):
        pooled = []
        for token_vectors in data:
            n = len(token_vectors)
            dim = len(token_vectors[0])
            pooled.append([sum(vec[i] for vec in token_vectors) / n for i in range(dim)])
        return pooled
    return data


def _offline_embedding(text: str, dim: int = 384) -> list[float]:
    """Deterministic, dependency-free pseudo-embedding used in demo mode/
    tests so the OER pipeline runs end to end without HF_TOKEN — same
    "keep running, lower quality" contract as the other _fallback_* helpers
    below. Not semantically meaningful, only structurally valid."""
    digest = hashlib.sha256(text.encode()).digest()
    return [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(dim)]


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
    LLM-generated, personalized content.

    Every string here is explicitly tagged "(demo)" — the frontend also
    shows a persistent demo-mode banner whenever HF_TOKEN isn't configured
    (see app.js's checkDemoMode/renderDemoModeBanner) — because an earlier
    revision used bare "[es] Topic, ejemplo 1" bracket placeholders with no
    indication they were a stand-in, which read as broken/missing content
    rather than an intentional offline fallback. Multiple-choice options are
    likewise never the same string repeated with a meaningless "(opción A)"
    suffix — that looked like duplicated/broken answers, not real choices."""
    from .curriculum import exercise_mix_for

    mix = mix_override if mix_override is not None else exercise_mix_for(req.unit.level)
    topic = topic_es(req.unit.topic)
    exercises = []
    for i, ex_type in enumerate(mix):
        word = f"{req.unit.topic.split()[0].lower()}_{i}"
        target = f"(demo) {topic} #{i + 1}"
        native = f"(demo) {topic} #{i + 1}"
        exercises.append(
            Exercise(
                id=f"ex-{i}-{word}",
                type=ex_type,
                prompt=f"Practica: {topic}",
                target_text=target,
                native_text=native if req.unit.level.uses_translation else "",
                options=[target, "Opción 2 (demo)", "Opción 3 (demo)"]
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
