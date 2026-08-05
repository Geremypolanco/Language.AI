"""Speech Router — unifies text-to-speech (both pipelines below) and
speech-to-text behind one interface:

    Speech -> Speech Router -> ideal model

Two distinct pipelines share the exact same synthesis engine chain (Piper
first, ElevenLabs/Parler-TTS for persona voices, MMS-TTS as the last resort
— see registry.py's AITask.SPEECH_SYNTHESIS and hf_client.text_to_speech),
so a teacher's voice sounds identical whether it was generated live or
ahead of time. Only what happens to the resulting audio bytes differs:

    Real-Time Voice:        text -> TTS -> streaming -> user      (Talk Live)
    Offline Voice Builder:  content -> TTS -> audio -> cache -> served forever
                             (academy_library/build.py, language_library/build.py,
                              via backend/ai/asset_pipeline.py)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import AsyncIterator

from ...config import settings
from ...hf_client import hf_client
from ..registry import AITask, chain_for

logger = logging.getLogger("lingua.ai.speech")

_MEDIA_EXT = {"audio/wav": "wav", "audio/flac": "flac", "audio/mpeg": "mp3"}


class SpeechRouter:
    @property
    def active_chain(self):
        return chain_for(AITask.SPEECH_SYNTHESIS)

    # ── Real-Time Voice pipeline ─────────────────────────────────────────

    async def synthesize(
        self, text: str, target_lang: str, voice_description: str | None = None, persona_id: str | None = None
    ) -> tuple[bytes, str] | None:
        return await hf_client.text_to_speech(text, target_lang, voice_description, persona_id)

    async def stream(
        self, text: str, target_lang: str, voice_description: str | None = None, persona_id: str | None = None
    ) -> AsyncIterator[tuple[str, bytes, str]]:
        async for sentence, audio, media_type in hf_client.stream_speech(
            text, target_lang, voice_description, persona_id
        ):
            yield sentence, audio, media_type

    async def transcribe(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
        return await hf_client.speech_to_text(audio_bytes, content_type)

    # ── Offline Voice Builder pipeline ───────────────────────────────────

    async def synthesize_asset(
        self,
        namespace: str,
        key: str,
        text: str,
        target_lang: str,
        *,
        voice_description: str | None = None,
        persona_id: str | None = None,
    ) -> str | None:
        """Synthesizes `text` at most once and persists it permanently under
        settings.audio_assets_dir — never LRU-evicted, unlike text_to_speech's
        own cache_dir cache (see cache_gc.py) — so a build pipeline can
        pre-generate every piece of narration/pronunciation audio a course
        will ever need exactly once, at build time, and serve it as a
        static file forever after. A real deployment fronts
        settings.audio_assets_dir with a CDN/object store the same way it
        already would for /public — that's the "cache -> CDN -> user" tier
        of the Offline Voice Builder diagram above; this function is the
        "cache" step, and main.py's static mount at /audio-assets is what
        makes the result directly servable.

        Idempotent: a second call with the same (namespace, key, target_lang,
        voice_description, persona_id, text) is a disk read, not a new
        synthesis call — safe to call on every build run, including resumed
        ones. Returns None only when text is empty or every synthesis
        provider genuinely fails, never partial/broken output."""
        text = text.strip()
        if not text:
            return None

        safe_namespace = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)
        digest = hashlib.sha256(
            f"{key}:{target_lang}:{voice_description or ''}:{persona_id or ''}:{text}".encode()
        ).hexdigest()[:24]
        asset_dir = os.path.join(settings.audio_assets_dir, safe_namespace)

        if os.path.isdir(asset_dir):
            for fname in os.listdir(asset_dir):
                if fname.startswith(f"{digest}."):
                    return f"/audio-assets/{safe_namespace}/{fname}"

        result = await self.synthesize(text, target_lang, voice_description, persona_id)
        if result is None:
            logger.info("Offline asset synthesis unavailable for namespace=%s key=%s", namespace, key)
            return None
        audio, media_type = result
        ext = _MEDIA_EXT.get(media_type, "bin")
        os.makedirs(asset_dir, exist_ok=True)
        filename = f"{digest}.{ext}"
        path = os.path.join(asset_dir, filename)
        tmp_path = f"{path}.part"
        with open(tmp_path, "wb") as f:
            f.write(audio)
        os.replace(tmp_path, path)
        return f"/audio-assets/{safe_namespace}/{filename}"
