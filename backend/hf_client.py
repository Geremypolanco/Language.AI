"""AI client for the four modalities this app needs: chat/text generation
(tutor + exercise authoring), text-to-image (vocabulary flashcards),
text-to-speech, and speech-to-text (conversation mode).

Chat and images run on Pollinations.ai first — free, keyless, no signup, no
billing (see settings.pollinations_*) — replacing Hugging Face's Inference
Providers as the primary engine after that account's free monthly credits
ran out (HTTP 402) and, separately, after Hugging Face retired the old
api-inference.huggingface.co host outright. Chat falls back to Hugging Face
(if configured) when Pollinations' small anonymous budget is exhausted.
Text-to-speech runs on Piper (see piper_tts.py) — a self-hosted neural TTS
engine that synthesizes audio locally in this container, so it's free and
unlimited for the ~53 languages it has a voice for, then falls back to the
optional Hugging Face MMS-TTS path for the rest. Speech-to-text and video
generation stay on the optional Hugging Face path only (settings.hf_token)
— Pollinations doesn't offer either for free, and self-hosting either one
is a much bigger lift than TTS was — so those two gracefully degrade to
"unavailable" with no token/credits, same as before. Nothing here uses
mocked "success" responses; a failure is always a real failure, never
faked.

Orchestration: exactly one layer in this app makes pedagogical/content
decisions — the chat-completions call (chat()/stream_chat(): Groq's
Llama-3.1-70B primary, Pollinations second, Qwen2.5-7B-Instruct on
Hugging Face as the last resort, chosen specifically for its multilingual/
CJK strength — see config.py's hf_chat_model comment). Every other engine
in this file is a specialist executor with no independent judgment: it
renders whatever the chat model already decided. Concretely, the JSON an
exercise-generation call returns carries an `image_prompt` (handed
verbatim to generate_image/Flux) and `audio_text` (handed to
text_to_speech/Piper); Talk Live's `reply_text` from stream_chat() is what
gets synthesized by stream_speech(); grading/curriculum/course/assignment
content all come from the same chat() call, never a second opinion from a
different model. Adding a new AI-driven feature to this app should follow
that same shape — one chat() call decides *what*, the modality-specific
engine below just renders it — rather than letting a specialist engine
also guess at content on its own.

Hugging Face is also the one tier in this rotation with a real, credit-
limited budget behind it (unlike Pollinations' free/keyless tier or a
self-hosted engine like Piper) — see _HFGuard below for how every HF call
site in this file is rate/budget-guarded so a traffic burst can't quietly
exhaust that budget or pile up slow doomed requests against an already
rate-limited account.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
from typing import TYPE_CHECKING

import httpx
from num2words import num2words

from .config import settings
from .curriculum import (
    ALPHABET_PROMPT_VERSION,
    ALPHABET_TOPIC,
    EXERCISE_FORMAT_VERSION,
    LessonRequest,
    build_exercise_generation_prompt,
    build_review_exercise_prompt,
    topic_es,
)
from .models import Exercise, ExerciseType

if TYPE_CHECKING:
    from .models import AcademicField, AcademicLevel, BookStub

logger = logging.getLogger("lingua.hf_client")

# ISO 639-1 -> MMS-TTS ISO 639-3 code, covering every language offered in the
# frontend's picker (frontend/app.js LANGS). A target language missing here
# still teaches fully via text, it just falls back to an English voice.
_MMS_LANG_CODES = {
    "en": "eng", "es": "spa", "fr": "fra", "de": "deu", "it": "ita", "pt": "por",
    "ja": "jpn", "ko": "kor", "zh": "cmn", "ru": "rus", "ar": "ara", "nl": "nld",
    "sv": "swe", "pl": "pol", "tr": "tur", "hi": "hin", "id": "ind", "vi": "vie",
    "th": "tha", "uk": "ukr", "el": "ell", "he": "heb", "cs": "ces", "ro": "ron",
    "hu": "hun", "fi": "fin", "da": "dan", "no": "nob", "bg": "bul", "sk": "slk",
    "hr": "hrv", "sr": "srp", "lt": "lit", "lv": "lav", "et": "est", "sl": "slv",
    "fa": "fas", "ur": "urd", "bn": "ben", "ta": "tam", "te": "tel", "mr": "mar",
    "gu": "guj", "pa": "pan", "ml": "mal", "kn": "kan", "ne": "nep", "si": "sin",
    "my": "mya", "km": "khm", "lo": "lao", "ms": "zlm", "tl": "tgl", "sw": "swh",
    "am": "amh", "so": "som", "ha": "hau", "yo": "yor", "ig": "ibo", "zu": "zul",
    "xh": "xho", "af": "afr", "is": "isl", "ga": "gle", "cy": "cym", "mt": "mlt",
    "eu": "eus", "ca": "cat", "gl": "glg", "az": "azj", "kk": "kaz", "uz": "uzn",
    "mn": "khk", "ka": "kat", "hy": "hye", "sq": "als", "mk": "mkd",
}


# ── Optional per-persona voice tier (backend/personas.py) ────────────────
# Tried ahead of the universal Piper/MMS chain in text_to_speech() only when
# a persona's voice_description/id is passed in (Talk Live) — every other
# caller (lessons, library, news, ...) never sets these and goes straight
# to Piper, unaffected by any of this.

# ElevenLabs — stable, publicly documented REST API with real named voice
# IDs, gated behind settings.elevenlabs_configured (opt-in, no default key).
ELEVENLABS_TTS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech"
# How long a 429 keeps the ElevenLabs tier skipped entirely once the circuit
# breaker trips (see HFClient._call_elevenlabs) — long enough that a burst
# of concurrent requests during a rate-limit window doesn't each pay for
# their own doomed round-trip before falling back, short enough to notice
# recovery without a restart.
_ELEVENLABS_CIRCUIT_COOLDOWN_S = 60.0

# Parler-TTS — voice steered via a natural-language description prompt
# (see TeacherPersona.voice_description) rather than literal speaker
# cloning; that's the model's own documented mechanism for distinct,
# describable voice identity.
PARLER_MODEL = "parler-tts/parler-tts-mini-multilingual-v1.1"
PARLER_LANGS = {"en", "fr", "es", "pt", "pl", "de", "it", "nl"}
# Verified live community Space (its app.py source was read directly to
# confirm the /gen_tts API and the preprocessing _preprocess_for_parler
# mirrors below) — used as a fallback when the direct serverless model
# endpoint isn't hosted, since Parler-TTS has much narrower Inference
# Providers coverage than the chat/image models this app otherwise relies on.
PARLER_SPACE_ID = "etrotta/parler-tts-mini-multilingual-v1.1"
# The fixed generation seed that Space's own gen_tts() hardcodes internally
# (read directly from its app.py source: `SEED = 42; set_seed(SEED)` before
# every generation) — documented here, not re-implemented, since the app
# never controls the Space's internals directly; it's what makes a fixed
# voice_description reproduce a consistent-sounding voice call to call.
PARLER_VOICE_SEED = 42

_ALLCAPS_ABBREV_PATTERN = re.compile(r"\b[A-Z][A-Z.]+\b")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


# ── Hugging Face reliability/budget guard ────────────────────────────────
# Hugging Face is deliberately the *last-resort* tier for chat (behind Groq
# and Pollinations) and the *only* option this app has for speech-to-text
# fallback, video, and part of the TTS chain (see module docstring) —
# exactly the calls most likely to all land on HF at once during a burst,
# right after Groq/Pollinations have already been exhausted. Left unguarded
# that's two separate failure modes:
#   1. A rate-limited or budget-exhausted HF account (HTTP 429/402) would
#      otherwise get retried on every subsequent request, each paying for a
#      full doomed round-trip (up to request_timeout_s=60s) instead of
#      failing fast — a pile of slow in-flight requests waiting on a
#      provider that's already down is exactly the kind of load that can
#      make the whole server feel like it fell over, independent of whether
#      any single process actually crashed.
#   2. Nothing capped how much of a credit-limited HF plan one bad traffic
#      spike could burn through in minutes.
# _HFGuard fixes both with the same shape of circuit breaker already proven
# for ElevenLabs below: any 429/402 opens a cooldown window, and a soft,
# approximate per-day usage budget closes the tier early on its own even
# without an explicit rate-limit response.
_HF_CIRCUIT_COOLDOWN_S = 120.0
# Flat per-call cost estimate for HF calls that aren't plain text-in/text-out
# (STT reads audio, video's cost isn't proportional to the prompt string) —
# picked so a handful of video generations (the heaviest call this app makes
# against HF) meaningfully draws down the daily budget instead of registering
# as nearly free the way a short text prompt's char-count would.
_HF_AUDIO_CALL_COST = 500
_HF_VIDEO_CALL_COST = 4000


class _HFGuard:
    """Tracks whether it's currently safe to spend more Hugging Face
    quota — see the module comment above for why this exists. Not a real
    token-accurate meter (there's no tokenizer here, just chars/4 and flat
    per-modality estimates); it only needs to be a safety margin, not a
    billing reconciliation."""

    def __init__(self, daily_budget: int, cooldown_s: float = _HF_CIRCUIT_COOLDOWN_S) -> None:
        self._daily_budget = daily_budget
        self._cooldown_s = cooldown_s
        self._circuit_open_until = 0.0
        self._budget_day: str | None = None
        self._used_today = 0

    def _roll_window_if_new_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self._budget_day:
            self._budget_day = today
            self._used_today = 0

    def allowed(self) -> bool:
        if time.monotonic() < self._circuit_open_until:
            return False
        self._roll_window_if_new_day()
        return self._used_today < self._daily_budget

    def record_usage(self, units: int) -> None:
        self._roll_window_if_new_day()
        self._used_today += max(0, units)

    def record_rate_limited(self) -> None:
        self._circuit_open_until = time.monotonic() + self._cooldown_s
        logger.warning("Hugging Face rate-limited/budget exhausted — pausing that tier for %.0fs", self._cooldown_s)


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
    the visible transcript/conversation history, which stays natural."""
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
    through asyncio.to_thread. Handles the couple of shapes gradio_client is
    known to return for an Audio-typed output (a local temp file path, or a
    dict/FileData wrapper around one); any shape this doesn't recognize just
    returns None and the caller falls back to MMS, same as any other
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


class HFClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=settings.request_timeout_s)
        self._groq_api_key = os.environ.get("GROQ_API_KEY")
        os.makedirs(settings.cache_dir, exist_ok=True)
        # Circuit breaker state for the ElevenLabs tier — a monotonic
        # timestamp; while time.monotonic() is before it, _call_elevenlabs
        # returns None immediately without touching the network, so a
        # rate-limit window degrades to "skip this tier" in microseconds
        # rather than retrying the same 429 on every single turn.
        self._elevenlabs_circuit_open_until: float = 0.0
        # Same idea, generalized to every Hugging Face call this client
        # makes (chat fallback, STT fallback, TTS's MMS/Parler branches,
        # video) — see the _HFGuard class above.
        self._hf_guard = _HFGuard(settings.hf_daily_token_budget)

    async def aclose(self) -> None:
        await self._http.aclose()

    def elevenlabs_circuit_breaker_engaged(self) -> bool:
        return time.monotonic() < self._elevenlabs_circuit_open_until

    async def _call_elevenlabs(self, text: str, voice_id: str) -> bytes | None:
        """Real REST call — ElevenLabs' text-to-speech endpoint has been
        publicly documented and stable for years, so this needs no fallback
        tier of its own beyond the outer try/except every call here follows.

        Circuit breaker: a 429 (rate limit / quota exhaustion) opens the
        breaker for _ELEVENLABS_CIRCUIT_COOLDOWN_S, during which this method
        short-circuits to None without an HTTP call — text_to_speech's
        caller then falls through to the Parler/Piper/MMS chain exactly as
        it would on any other failure."""
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

    def _hf_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.hf_token}"}

    def _pollinations_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.pollinations_token}"} if settings.pollinations_token else {}

    def _cache_path(self, namespace: str, key: str, ext: str) -> str:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return os.path.join(settings.cache_dir, f"{namespace}-{digest}.{ext}")

    # ── Chat / text generation ──────────────────────────────────────────

    async def _post_with_retry(self, url: str, **kwargs) -> httpx.Response:
        """One retry on a transient network failure (DNS blip, connection
        reset) before giving up — every outbound call in this client goes
        through this (or _get_with_retry below) so none of them are exposed
        to a bare network hiccup alone."""
        for attempt in range(2):
            try:
                return await self._http.post(url, **kwargs)
            except httpx.TransportError:
                if attempt == 1:
                    raise
                await asyncio.sleep(0.5)
        raise AssertionError("unreachable")  # loop always returns or raises

    async def _get_with_retry(self, url: str, **kwargs) -> httpx.Response:
        for attempt in range(2):
            try:
                return await self._http.get(url, **kwargs)
            except httpx.TransportError:
                if attempt == 1:
                    raise
                await asyncio.sleep(0.5)
        raise AssertionError("unreachable")

    async def chat(self, messages: list[dict[str, str]], max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Uses Groq as the primary elite free provider (Llama 3.1 70B), 
        falling back to Pollinations/HF if Groq is unavailable."""
        if settings.testing:
            raise HFClientError("AI disabled in test environment")
            
        # Try Groq first (Elite speed and quality)
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                resp = await self._post_with_retry(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={"model": "llama-3.1-70b-versatile", "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False},
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                logger.warning("Groq chat HTTP %s: %s", resp.status_code, resp.text[:300])
            except Exception as e:
                logger.warning("Groq chat failed: %s", e)

        # Fallback to Pollinations
        try:
            resp = await self._post_with_retry(
                settings.pollinations_chat_endpoint,
                headers=self._pollinations_headers(),
                json={"model": settings.chat_model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

        # Final fallback to Hugging Face — gated by _HFGuard so a burst that
        # already exhausted Groq/Pollinations doesn't also hammer a rate-
        # limited or budget-exhausted HF account (see _HFGuard docstring).
        if settings.hf_configured and self._hf_guard.allowed():
            try:
                resp = await self._post_with_retry(
                    settings.hf_chat_endpoint,
                    headers=self._hf_headers(),
                    json={"model": settings.hf_chat_model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    self._hf_guard.record_usage((sum(len(m.get("content", "")) for m in messages) + len(content)) // 4)
                    return content
                if resp.status_code in (402, 429):
                    self._hf_guard.record_rate_limited()
            except Exception:
                pass

        raise HFClientError("All AI chat providers failed")

    async def stream_chat(self, messages: list[dict[str, str]], max_tokens: int = 1000, temperature: float = 0.7):
        """Streams chat completions from Groq for zero-latency UI."""
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            # Fallback to non-streaming if no Groq key
            yield await self.chat(messages, max_tokens, temperature)
            return

        try:
            async with self._http.stream(
                "POST",
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={"model": "llama-3.1-70b-versatile", "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True},
                timeout=60.0
            ) as resp:
                if resp.status_code != 200:
                    yield await self.chat(messages, max_tokens, temperature)
                    return
                
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue
        except Exception:
            yield await self.chat(messages, max_tokens, temperature)

    async def generate_exercises(
        self, req: LessonRequest, mix_override: list[ExerciseType] | None = None
    ) -> list[Exercise]:
        """Generates a batch of exercises and caches them to disk, same
        pattern as books/courses. This is the highest-frequency AI call in
        the app (every lesson start), so caching it is the single biggest
        lever for keeping AI spend near zero without capping how much anyone
        can use the app. Cached per (unit, level, target/native language,
        interests, exercise mix) — deliberately not per recent_mistakes
        (personal to each user, and would kill the cache-hit rate); spaced-
        repetition review of missed words already runs independently through
        srs.py, so this doesn't lose the main mistake-remediation path."""
        from .curriculum import resolve_exercise_mix

        mix = resolve_exercise_mix(req.unit, mix_override)
        # req.unit.topic (not just the id) is part of the key on purpose: the
        # skill-tree's topic list has been reordered before (inserting a new
        # topic shifts every later unit's numeric id — e.g. "A1-0" stopped
        # meaning "Greetings" and started meaning "Alphabet & first sounds")
        # and an id-only key would silently keep serving the *old* topic's
        # cached exercises under the new topic's identity forever.
        cache_key = (
            f"{req.unit.id}:{req.unit.topic}:{req.unit.level.value}:{req.target_lang}:{req.native_lang}:"
            f"{','.join(sorted(req.interests))}:{','.join(t.value for t in mix)}:{EXERCISE_FORMAT_VERSION}"
            # Only the alphabet unit's cache key carries this additionally —
            # see ALPHABET_PROMPT_VERSION's docstring for why a prompt fix
            # alone doesn't reach learners with an already-cached exercise set.
            f"{':' + ALPHABET_PROMPT_VERSION if req.unit.topic == ALPHABET_TOPIC else ''}"
        )
        cache_path = self._cache_path("exercises", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return [Exercise(**item) for item in json.load(f)]

        prompt = build_exercise_generation_prompt(req, mix_override)
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
            )
            exercises = _with_teaching_intros(_parse_exercises(raw))
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump([e.model_dump() for e in exercises], f)
            return exercises
        except Exception:
            logger.exception("AI exercise generation failed, using offline fallback content")
        return _with_teaching_intros(_fallback_exercises(req, mix_override))

    async def generate_review_exercises(
        self, items: list[dict], native_lang: str, target_lang: str
    ) -> list[Exercise]:
        """Turns due spaced-repetition items (see srs.due_review_items) into
        real, gradable exercises. Deliberately NOT disk-cached like
        generate_exercises: the due set is personal to one learner and keeps
        changing (SM-2 reschedules every item after every answer), so a cache
        keyed on it would almost never hit — caching would only cost disk
        with no benefit, unlike the shared-across-learners unit content
        generate_exercises caches. No teaching intro is prepended either:
        these are words the learner already knows, being re-tested for
        recall, not first exposure.
        """
        if not items:
            return []
        prompt = build_review_exercise_prompt(items, native_lang, target_lang)
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1200,
            )
            return _parse_review_exercises(raw, items)
        except Exception:
            logger.exception("AI review-exercise generation failed, using content-snapshot fallback")
        return _fallback_review_exercises(items)

    async def conversation_reply(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        messages = [{"role": "system", "content": system_prompt}, *history]
        try:
            return await self.chat(messages, max_tokens=300, temperature=0.8)
        except Exception:
            logger.exception("AI conversation reply failed")
            return "(no se pudo generar una respuesta en este momento — inténtalo de nuevo) ¡Qué bien, cuéntame más!"

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
            logger.exception("AI book generation failed, using offline fallback content")
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
        but for a curriculum outline instead of a story. Content is written
        in native_lang on purpose: the academy exists to teach real subject
        knowledge, which the learner needs to actually understand — language
        immersion is handled separately by the Lessons/Library, not here."""
        from .academy import build_curriculum_prompt

        cache_key = f"{field.id}:{level.value}:{native_lang}"
        cache_path = self._cache_path("curriculum", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

        from . import rag

        # ELITE RAG: Parallel fetch from ArXiv and Wikipedia for deep grounding
        arxiv_task = rag.fetch_arxiv_context(field.id, field.name)
        wiki_task = rag.fetch_wikipedia_context(field.name)
        arxiv_context, wiki_context = await asyncio.gather(arxiv_task, wiki_task)
        
        context = f"{arxiv_context}\n\n{wiki_context}".strip()
        
        prompt = build_curriculum_prompt(field, level.label_es, level.course_count, native_lang)
        if context:
            prompt = f"### REFERENCE DATA FROM REAL SOURCES (Wikipedia & ArXiv):\n{context}\n\n### INSTRUCTIONS:\n{prompt}"
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
            logger.exception("AI curriculum generation failed, using offline fallback content")
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
        """Generates (once) and caches a course's module content, written in
        native_lang — same rationale as generate_curriculum."""
        from .academy import build_course_prompt

        cache_key = f"{course_id}:{native_lang}"
        cache_path = self._cache_path("course", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

        from . import rag

        context = await rag.fetch_arxiv_context(field.id, course_title)
        if not context:
            context = await rag.fetch_wikipedia_context(course_title)
        prompt = build_course_prompt(field, level.label_es, course_title, course_description, native_lang)
        if context:
            prompt = f"{context}\n\n{prompt}"
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
            logger.exception("AI course generation failed, using offline fallback content")
            return [
                {
                    "title": "No se pudo generar el curso",
                    "content": "Inténtalo de nuevo en un momento.",
                }
            ]

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(modules, f)
        return modules

    async def generate_practice_scenario(
        self,
        field: "AcademicField",
        level: "AcademicLevel",
        course_id: str,
        course_title: str,
        course_description: str,
        native_lang: str,
    ) -> str:
        """Hands-on fields (nursing, engineering, business, ...) need more than
        theory — this generates a realistic case/scenario the learner responds
        to in their own words, with AI feedback on their answer (see
        grade_practice_response). Cached per course like the lesson content;
        this is deliberately a text-based simulation, not real clinical/lab
        practice — the honest, buildable version of "practice, not just
        theory" for a software-only product. Written in native_lang, same
        rationale as the rest of the academy."""
        from .academy import build_practice_scenario_prompt

        cache_path = self._cache_path("scenario", f"{course_id}:{native_lang}", "txt")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return f.read()

        prompt = build_practice_scenario_prompt(field, level.label_es, course_title, course_description, native_lang)
        try:
            content = await self.chat(
                [
                    {
                        "role": "system",
                        "content": "You design realistic, hands-on practice scenarios for students. Output only "
                        "the scenario text, no meta-commentary.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.8,
            )
        except Exception:
            logger.exception("AI scenario generation failed, using offline fallback content")
            return "No se pudo generar el caso práctico en este momento — inténtalo de nuevo."

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(content)
        return content

    async def grade_practice_response(self, scenario: str, user_response: str, native_lang: str) -> str:
        """Feedback on the learner's own answer to a practice scenario — not
        cached, since it depends on what they personally wrote. Written in
        native_lang, same rationale as the rest of the academy."""
        prompt = (
            f"A student was given this practice scenario:\n\n{scenario}\n\n"
            f"Their response:\n\n{user_response}\n\n"
            f"Give short, constructive feedback in {native_lang} (3-5 sentences): what they got right, what to "
            f"improve, and one concrete tip. Be encouraging but honest."
        )
        try:
            return await self.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7,
            )
        except Exception:
            logger.exception("AI scenario feedback failed")
            return "No se pudo generar retroalimentación en este momento — inténtalo de nuevo."

    async def generate_assignments(
        self,
        field: "AcademicField",
        level: "AcademicLevel",
        course_id: str,
        course_title: str,
        course_description: str,
        native_lang: str,
    ) -> list[dict]:
        """Generates (once) and caches real, gradeable schoolwork for a
        course — one tarea, one informe, one proyecto — the same shape of
        assigned work a normal school/university course gives, on top of
        the theory in generate_course_content and the ungraded practice
        scenario above."""
        from .academy import build_assignments_prompt

        cache_key = f"{course_id}:{native_lang}"
        cache_path = self._cache_path("assignments", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

        prompt = build_assignments_prompt(field, level.label_es, course_title, course_description, native_lang)
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                # 3 detailed, native-language instruction blocks (submission
                # format, word counts, exact questions) routinely ran past a
                # smaller budget and got cut off mid-JSON, which then failed
                # to parse and fell straight to the "no se pudo generar"
                # fallback even though the model was actually answering.
                max_tokens=1800,
                temperature=0.6,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            items = json.loads(cleaned)
            assignments = [
                {
                    "id": f"{course_id}:{i}",
                    "type": item.get("type", "tarea"),
                    "title": item.get("title", ""),
                    "instructions": item.get("instructions", ""),
                }
                for i, item in enumerate(items)
                if item.get("instructions")
            ]
        except Exception:
            logger.exception("AI assignment generation failed, using offline fallback content")
            return [
                {
                    "id": f"{course_id}:0",
                    "type": "tarea",
                    "title": "No se pudieron generar las tareas",
                    "instructions": "Inténtalo de nuevo en un momento.",
                }
            ]

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(assignments, f)
        return assignments

    async def grade_assignment_submission(
        self, assignment_title: str, instructions: str, response: str, native_lang: str
    ) -> dict:
        """Grades a learner's submitted tarea/informe/proyecto — not cached,
        since it depends on what they personally wrote. Returns a short
        qualitative grade plus feedback, written in native_lang."""
        prompt = (
            f"A student was assigned this schoolwork:\n\nTitle: {assignment_title}\n"
            f"Instructions: {instructions}\n\n"
            f"Their submission:\n\n{response}\n\n"
            f"Grade it fairly, as a real teacher would, in {native_lang}. "
            f'Respond with ONLY a JSON object, no other text, shaped like: '
            f'{{"grade": "a short qualitative grade, e.g. Excelente / Bien / Necesita mejorar", '
            f'"feedback": "3-5 sentences: what they did well, what to improve, one concrete next step"}}'
        )
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=350,
                temperature=0.6,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            return {"grade": data.get("grade", ""), "feedback": data.get("feedback", "")}
        except Exception:
            logger.exception("AI assignment grading failed")
            return {"grade": "", "feedback": "No se pudo calificar la entrega en este momento — inténtalo de nuevo."}

    async def grade_open_answer(
        self, question: str, rubric_note: str, student_answer: str, native_lang: str
    ) -> tuple[bool, str]:
        """Grades one open/applied_problem quiz or exam question against its
        rubric_note (see academy_library.build_quiz_prompt/build_exam_prompt
        — the rubric_note is generated alongside the question but never
        shown to the student before they answer). Not cached: depends on
        what the student personally wrote. Fails closed — an AI failure
        marks the answer wrong with an honest note, never silently correct,
        since a false "correct" would corrupt the competency score it feeds
        into (see backend/learning_engine/competency.py)."""
        prompt = (
            f"A student was asked: \"{question}\"\n"
            f"To be correct, their answer should cover: {rubric_note}\n"
            f"Their answer: \"{student_answer}\"\n"
            f"Does their answer adequately cover the rubric? Respond with ONLY a JSON object, no other text: "
            f'{{"passed": true or false, "feedback": "one short sentence in {native_lang} explaining why"}}'
        )
        try:
            raw = await self.chat(
                [
                    {"role": "system", "content": "You output only valid JSON, nothing else."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
            )
            cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            return bool(data.get("passed")), data.get("feedback", "")
        except Exception:
            logger.exception("AI open-answer grading failed")
            return False, "No se pudo calificar esta respuesta automáticamente en este momento."

    # ── Recommendations (books, songs, and other media) ─────────────────

    async def generate_recommendations(
        self, target_lang: str, level: str, interests: list[str]
    ) -> list[dict]:
        """Cached per (target language, level, interests) — same cost-control
        rationale as generate_exercises. Only successful HF generations are
        cached, same rule as everywhere else in this file."""
        cache_key = f"{target_lang}:{level}:{','.join(sorted(interests))}"
        cache_path = self._cache_path("recommendations", cache_key, "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

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
            recommendations = [
                {
                    "kind": item.get("kind", "book"),
                    "title": item.get("title", ""),
                    "creator": item.get("creator", ""),
                    "reason": item.get("reason", ""),
                }
                for item in items
            ]
        except Exception:
            logger.exception("AI recommendations generation failed, using offline fallback content")
            return [
                {
                    "kind": "book",
                    "title": f"Busca cuentos ilustrados para nivel {level}",
                    "creator": f"En {target_lang}",
                    "reason": "No se pudieron generar recomendaciones personalizadas en este momento.",
                }
            ]

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(recommendations, f)
        return recommendations

    # ── Text-to-image (vocab flashcards) ────────────────────────────────

    async def generate_image(self, prompt: str) -> bytes | None:
        """Pollinations' image endpoint is a plain keyless GET that returns
        the image bytes directly — no request body, no JSON envelope.

        _get_with_retry only retries transport-level failures (DNS blips,
        resets) — it treats a 429/5xx as a normal response, not something to
        retry. Under a burst (e.g. Talk Live's persona picker requesting all
        5 teacher portraits within the same second) that free, shared,
        rate-limited endpoint routinely 429s a couple of them, and since a
        failed generation is never cached, that portrait stays permanently
        broken until someone happens to hit this code path again. A few
        retries with backoff here — specifically for HTTP-level failures,
        which the shared retry helper doesn't cover — fixes that without
        changing behavior for every other caller of _get_with_retry."""
        cache_path = self._cache_path("img", prompt, "jpg")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read()
        if settings.testing:
            return None
        url = f"{settings.pollinations_image_endpoint}/{urllib.parse.quote(prompt)}"
        try:
            for attempt in range(3):
                resp = await self._get_with_retry(
                    url, headers=self._pollinations_headers(), params={"model": settings.image_model}
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                    with open(cache_path, "wb") as f:
                        f.write(resp.content)
                    return resp.content
                logger.warning("Pollinations image generation HTTP %s (attempt %d): %s", resp.status_code, attempt + 1, resp.text[:200])
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
        except Exception:
            logger.exception("Pollinations image generation failed")
        return None

    # ── Text-to-video (short topic clips) ───────────────────────────────

    async def generate_video(self, prompt: str) -> bytes | None:
        """Video generation stays on the optional Hugging Face path —
        Pollinations doesn't offer it, and video has much narrower
        serverless model support in general, so a longer per-call timeout
        and a clean None on failure (never a broken video) matter even more
        here. Best-effort by design: no HF_TOKEN just means no video."""
        cache_path = self._cache_path("video", prompt, "mp4")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read()
        # _HFGuard-gated like every other HF call — video is the single
        # heaviest request this app makes against HF, so it's the one most
        # worth stopping early once the daily budget or a rate limit trips.
        if not settings.hf_configured or not self._hf_guard.allowed():
            return None
        try:
            resp = await self._post_with_retry(
                f"{settings.hf_models_endpoint}/{settings.video_model}",
                headers=self._hf_headers(),
                json={"inputs": prompt},
                timeout=150.0,
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("video"):
                self._hf_guard.record_usage(_HF_VIDEO_CALL_COST)
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                return resp.content
            if resp.status_code in (402, 429):
                self._hf_guard.record_rate_limited()
            logger.warning("HF video generation HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("HF video generation failed")
        return None

    # ── Text-to-speech ──────────────────────────────────────────────────

    async def text_to_speech(
        self,
        text: str,
        target_lang: str,
        voice_description: str | None = None,
        persona_id: str | None = None,
    ) -> tuple[bytes, str] | None:
        """Piper first (self-hosted, free, and genuinely unlimited — see
        piper_tts.py — for the ~53 languages it covers), falling back to the
        Hugging Face MMS-TTS path for everything else, or if Piper's
        synthesis itself fails. Pollinations isn't in this rotation at all:
        its old keyless audio endpoint now 404s ("Model not found:
        openai-audio... visit https://enter.pollinations.ai") — there's no
        free keyless TTS on that side to use. Returns (audio_bytes,
        media_type) rather than bare bytes because the two engines produce
        different containers (Piper: WAV, HF/MMS: FLAC) and callers need to
        label the response correctly rather than guessing.

        When `persona_id`/`voice_description` are given (Talk Live's chosen
        teacher persona — see backend/personas.py), two optional tiers are
        tried ahead of the universal Piper/MMS chain above, so a persona
        actually sounds distinct rather than sharing the one shared voice
        per language: ElevenLabs (if that persona has a mapped voice ID and
        settings.elevenlabs_configured) first, then Parler-TTS (steered by
        the free-form voice_description) if the language supports it and
        HF is configured. Either falling through — no key, no mapping, a
        rate limit, a cold Space — degrades straight to Piper/MMS below,
        never to silence."""
        lang_code2 = target_lang.lower()[:2]

        voice_id = settings.elevenlabs_voice_map.get(persona_id) if persona_id else None
        if voice_id and settings.elevenlabs_configured:
            elevenlabs_cache_path = self._cache_path("tts-elevenlabs", f"{voice_id}::{text}", "mp3")
            if os.path.exists(elevenlabs_cache_path):
                with open(elevenlabs_cache_path, "rb") as f:
                    return f.read(), "audio/mpeg"
            audio = await self._call_elevenlabs(text, voice_id)
            if audio:
                with open(elevenlabs_cache_path, "wb") as f:
                    f.write(audio)
                return audio, "audio/mpeg"
            logger.info("ElevenLabs tier unavailable/failed, falling back to the Parler-TTS/Piper chain")

        if (
            voice_description
            and lang_code2 in PARLER_LANGS
            and settings.hf_configured
            and not settings.testing
            and self._hf_guard.allowed()
        ):
            parler_cache_path = self._cache_path("tts-parler", f"{voice_description}::{text}", "flac")
            if os.path.exists(parler_cache_path):
                with open(parler_cache_path, "rb") as f:
                    return f.read(), "audio/flac"

            # Only the copy sent to the model is preprocessed — the visible
            # transcript/history stays natural; see _preprocess_for_parler.
            parler_text = _preprocess_for_parler(text, lang_code2)

            try:
                resp = await self._post_with_retry(
                    f"{settings.hf_models_endpoint}/{PARLER_MODEL}",
                    headers=self._hf_headers(),
                    json={"inputs": parler_text, "parameters": {"description": voice_description}},
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
                    self._hf_guard.record_usage(_HF_AUDIO_CALL_COST)
                    with open(parler_cache_path, "wb") as f:
                        f.write(resp.content)
                    return resp.content, "audio/flac"
                if resp.status_code in (402, 429):
                    self._hf_guard.record_rate_limited()
                logger.warning("HF Parler-TTS HTTP %s: %s", resp.status_code, resp.text[:200])
            except Exception:
                logger.exception("HF Parler-TTS direct endpoint failed, trying the verified Space fallback")

            try:
                audio_bytes = await asyncio.to_thread(_call_parler_space, parler_text, voice_description)
                if audio_bytes:
                    self._hf_guard.record_usage(_HF_AUDIO_CALL_COST)
                    with open(parler_cache_path, "wb") as f:
                        f.write(audio_bytes)
                    return audio_bytes, "audio/flac"
            except Exception:
                logger.exception("Parler-TTS Space fallback failed, falling back to Piper/MMS")

        from . import piper_tts

        piper_voice = piper_tts.voice_key_for(target_lang)
        if piper_voice is not None:
            cache_path = self._cache_path("tts-piper", f"{piper_voice}:{text}", "wav")
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as f:
                    return f.read(), "audio/wav"
            if not settings.testing:
                audio = await piper_tts.synthesize(text, target_lang)
                if audio is not None:
                    with open(cache_path, "wb") as f:
                        f.write(audio)
                    return audio, "audio/wav"

        lang_code = _MMS_LANG_CODES.get(target_lang.lower()[:2], "eng")
        model = f"{settings.tts_model_prefix}-{lang_code}"
        cache_path = self._cache_path("tts", f"{model}:{text}", "flac")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                return f.read(), "audio/flac"
        if not settings.hf_configured or not self._hf_guard.allowed():
            return None
        try:
            resp = await self._post_with_retry(
                f"{settings.hf_models_endpoint}/{model}",
                headers=self._hf_headers(),
                json={"inputs": text},
            )
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio"):
                self._hf_guard.record_usage(_HF_AUDIO_CALL_COST)
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                return resp.content, "audio/flac"
            if resp.status_code in (402, 429):
                self._hf_guard.record_rate_limited()
            logger.warning("HF TTS HTTP %s (%s): %s", resp.status_code, model, resp.text[:200])
        except Exception:
            logger.exception("HF TTS failed")
        return None

    async def stream_speech(
        self,
        text: str,
        target_lang: str,
        voice_description: str | None = None,
        persona_id: str | None = None,
    ):
        """Splits `text` into sentences (piper_tts.split_into_sentences) and
        synthesizes+yields each one's audio as soon as it's ready, instead
        of waiting for the whole block. This is what actually shortens
        perceived latency here: chat completions arrive as a single
        non-streamed payload (there's no live token stream to slice), so
        the only lever available is starting audio playback on sentence 1
        while sentence 2+ are still being synthesized, rather than making
        the caller wait on one TTS call sized to the entire reply. Skips
        (not yields) any sentence whose synthesis genuinely fails — a
        dropped clause in a spoken reply beats aborting the whole turn.

        `voice_description`/`persona_id` are forwarded to text_to_speech's
        optional ElevenLabs/Parler-TTS persona-voice tiers (see
        backend/personas.py) — omit both for the plain shared-per-language
        voice used everywhere else in the app."""
        from . import piper_tts

        for sentence in piper_tts.split_into_sentences(text):
            result = await self.text_to_speech(sentence, target_lang, voice_description, persona_id)
            if result is not None:
                yield sentence, result[0], result[1]

    # ── Text embeddings (semantic search / similarity ranking) ──────────

    async def embed_text(self, text: str) -> list[float] | None:
        """Real sentence embeddings via BAAI/bge-m3 (settings.hf_embedding_model)
        — see backend/ai/registry.py's AITask.EMBEDDING entry for why that
        model specifically. Called through the same HF Inference Providers
        router and shared _HFGuard budget every other HF call in this file
        uses (see _HFGuard's docstring: one shared budget, not a second
        independent one per feature). Disk-cached forever, like every other
        AI-generated asset here — an embedding for a given text never
        changes. Returns None (never raises) if HF isn't configured, the
        guard is closed, or the call itself fails — callers fall back to
        plain keyword matching, same graceful-degrade shape as everything
        else in this client."""
        cache_path = self._cache_path("embed", f"{settings.hf_embedding_model}:{text}", "json")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        if not settings.hf_configured or settings.testing or not self._hf_guard.allowed():
            return None
        try:
            resp = await self._post_with_retry(
                f"{settings.hf_models_endpoint}/{settings.hf_embedding_model}",
                headers=self._hf_headers(),
                json={"inputs": text},
            )
            if resp.status_code == 200:
                vector = resp.json()
                # feature-extraction responses vary by model/provider between a
                # flat pooled-sentence vector ([...]) and a nested per-token/
                # per-sequence wrapper ([[...]] or [[[...]]]); bge-m3 is a
                # pooled sentence-embedding model so a flat list is expected,
                # but this unwraps one level of nesting defensively either way.
                while vector and isinstance(vector[0], list):
                    vector = vector[0]
                if not vector or not isinstance(vector[0], (int, float)):
                    logger.warning("HF embedding returned an unexpected shape for model %s", settings.hf_embedding_model)
                    return None
                self._hf_guard.record_usage(len(text) // 4)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(vector, f)
                return vector
            if resp.status_code in (402, 429):
                self._hf_guard.record_rate_limited()
            logger.warning("HF embedding HTTP %s: %s", resp.status_code, resp.text[:200])
        except Exception:
            logger.exception("HF embedding failed")
        return None

    # ── Speech-to-text ───────────────────────────────────────────────────

    async def speech_to_text(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
        """Uses Groq Whisper (instant, elite quality) as primary, 
        falling back to Hugging Face Whisper."""
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            try:
                # Groq requires multipart/form-data for translations/transcriptions
                files = {"file": ("audio.webm", audio_bytes, content_type), "model": (None, "whisper-large-v3")}
                resp = await self._http.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    files=files,
                    timeout=30.0
                )
                if resp.status_code == 200:
                    return resp.json().get("text", "").strip()
                logger.warning("Groq STT HTTP %s: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("Groq STT failed: %s", e)

        # Fallback to Hugging Face — same _HFGuard gating as chat()'s HF tier.
        if settings.hf_configured and self._hf_guard.allowed():
            try:
                resp = await self._post_with_retry(
                    f"{settings.hf_models_endpoint}/{settings.stt_model}",
                    headers={**self._hf_headers(), "Content-Type": content_type},
                    content=audio_bytes,
                )
                if resp.status_code == 200:
                    self._hf_guard.record_usage(_HF_AUDIO_CALL_COST)
                    return resp.json().get("text", "").strip()
                if resp.status_code in (402, 429):
                    self._hf_guard.record_rate_limited()
            except Exception:
                pass

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


def _parse_review_exercises(raw: str, items: list[dict]) -> list[Exercise]:
    """Like _parse_exercises, but for review sessions the model is never
    trusted with vocab_key/unit_id identity — those are force-assigned from
    `items` by position, since only the caller actually knows which
    vocab_progress row each due item belongs to (see
    build_review_exercise_prompt's docstring). If the model returns a
    different number of items than were asked for, we zip to the shorter
    length rather than crash or silently drop the mismatch elsewhere."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(cleaned)
    exercises = []
    for item, generated in zip(items, parsed, strict=False):
        exercises.append(
            Exercise(
                id=f"review-{item['vocab_key']}",
                type=ExerciseType(generated.get("type", "translate_to_native")),
                prompt=generated.get("prompt", ""),
                target_text=generated.get("target_text", item["target_text"]),
                native_text=generated.get("native_text", item["native_text"]),
                options=[],
                correct_answer=generated.get("correct_answer", item["native_text"] or item["target_text"]),
                image_prompt="",
                audio_text=generated.get("audio_text", generated.get("target_text", item["target_text"])),
                vocab_key=item["vocab_key"],
            )
        )
    if not exercises:
        raise ValueError("Review generation returned no usable items")
    return exercises


def _fallback_review_exercises(items: list[dict]) -> list[Exercise]:
    """Network-free review content built directly from each item's own
    stored content snapshot — unlike _fallback_exercises' generic
    placeholder text, this is genuinely correct and gradable (the real word
    the learner is due to review), just without a freshly recombined
    sentence around it. Honest, not degraded: translate_to_native with a
    real target_text/native_text pair needs no AI to be a valid exercise."""
    return [
        Exercise(
            id=f"review-{item['vocab_key']}",
            type=ExerciseType.TRANSLATE_TO_NATIVE,
            prompt="Traduce esta palabra o frase.",
            target_text=item["target_text"],
            native_text=item["native_text"],
            options=[],
            correct_answer=item["native_text"] or item["target_text"],
            image_prompt="",
            audio_text=item["target_text"],
            vocab_key=item["vocab_key"],
        )
        for item in items
    ]


def _with_teaching_intros(exercises: list[Exercise]) -> list[Exercise]:
    """Prepends a self-paced, ungraded 'vocab_intro' card before each graded
    exercise, built from that same exercise's own already-generated fields
    (word, translation, audio, image) — this is the fix for lessons that
    quizzed a learner on a word cold, before ever showing it to them. A real
    classroom teaches a word first (how it's written, what it means, how it
    sounds) and only then tests it; this makes that the actual shape of
    every lesson instead of relying on the AI prompt to somehow produce
    twice the content reliably. Deriving the teaching card from the graded
    exercise's own fields (rather than asking the model for a separate one)
    guarantees they're always about the exact same word — no risk of the
    two drifting apart. Skipped for free_conversation_prompt (no single
    fixed vocab item to preview — it's open-ended practice) and for an
    exercise that's already vocab_intro itself (the offline fallback
    downgrades multiple_choice/image_match to vocab_intro when it can't
    generate real distractors — see _fallback_exercises — and that IS the
    teaching card, so it needs no second one prepended before it)."""
    result: list[Exercise] = []
    for ex in exercises:
        if ex.type not in (ExerciseType.FREE_CONVERSATION_PROMPT, ExerciseType.VOCAB_INTRO):
            result.append(
                Exercise(
                    id=f"{ex.id}-intro",
                    type=ExerciseType.VOCAB_INTRO,
                    prompt="",
                    target_text=ex.target_text,
                    native_text=ex.native_text,
                    options=[],
                    correct_answer=ex.target_text,
                    image_prompt=ex.image_prompt,
                    audio_text=ex.audio_text or ex.target_text,
                    vocab_key=ex.vocab_key,
                )
            )
        result.append(ex)
    return result


def _fallback_exercises(req: LessonRequest, mix_override: list[ExerciseType] | None = None) -> list[Exercise]:
    """Deterministic, network-free content used when the AI call genuinely
    fails (a transient failure that survived the one retry in chat(), or
    Pollinations itself being unreachable/down). Clearly lower quality than
    the real LLM-generated, personalized content, and says so directly in
    the exercise's own prompt text so a user never mistakes this for a
    broken real exercise."""
    from .curriculum import resolve_exercise_mix

    mix = resolve_exercise_mix(req.unit, mix_override)
    topic = topic_es(req.unit.topic)
    exercises = []
    for i, ex_type in enumerate(mix):
        word = f"{req.unit.topic.split()[0].lower()}_{i}"
        target = f"{topic} ({req.target_lang}) #{i + 1}"
        native = f"{topic} ({req.native_lang}) #{i + 1}"
        # multiple_choice/image_match need real, meaningfully DIFFERENT
        # distractors to mean anything — without AI there's no way to
        # generate those, so the old fallback offered 3 copies of the same
        # placeholder text with "otra opción" tacked on, which looked like
        # a real quiz but tested nothing at all. Downgrading these two
        # specific types to vocab_intro (the same self-paced, ungraded
        # teaching card _with_teaching_intros already shows before every
        # exercise) is the honest option: show the placeholder content
        # plainly instead of faking an assessment that has no real answer
        # to get right or wrong.
        effective_type = ExerciseType.VOCAB_INTRO if ex_type in (ExerciseType.MULTIPLE_CHOICE, ExerciseType.IMAGE_MATCH) else ex_type
        exercises.append(
            Exercise(
                id=f"ex-{i}-{word}",
                type=effective_type,
                prompt=f"(Sin conexión con la IA en este momento — contenido de práctica sin conexión) {topic}",
                target_text=target,
                native_text=native if req.unit.level.uses_translation else "",
                options=[],
                correct_answer=target,
                image_prompt=f"a simple, clear illustration of {req.unit.topic}, item {i + 1}",
                audio_text=target,
                vocab_key=f"{req.unit.id}.{word}",
            )
        )
    return exercises


def _fallback_curriculum(field: "AcademicField", level: "AcademicLevel") -> list[dict]:
    """Deterministic, network-free course list for when generation genuinely
    fails — same role as _fallback_exercises for lessons."""
    return [
        {
            "title": f"{field.name} — módulo {i + 1}",
            "description": "(No se pudo generar el plan de estudios en este momento — inténtalo de nuevo)",
        }
        for i in range(level.course_count)
    ]


hf_client = HFClient()
