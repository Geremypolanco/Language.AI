"""Self-hosted, free, unlimited text-to-speech via Piper
(https://github.com/OHF-Voice/piper1-gpl) — a small, fast neural TTS engine
that runs entirely inside this container. Chosen specifically to close the
gap left by Pollinations dropping free keyless audio and Hugging Face's
Inference Providers credits being exhausted (see hf_client.py's module
docstring): unlike both of those, this needs no external API, no billing,
and no rate limit at all — it's just local computation.

License note: piper-tts >=1.3 is GPL-3.0-or-later (the original MIT-licensed
rhasspy/piper was archived; development moved to OHF-Voice/piper1-gpl). The
last MIT release (1.2.0) depends on the separate `piper-phonemize` package,
which has no Linux wheel for Python 3.12 — it doesn't install on this
project's `python:3.12-slim` image. piper-tts 1.6.0 ships a proper
manylinux/cp39-abi3 wheel with phonemization bundled in, so that's what's
pinned here. GPL-3.0 copyleft triggers on *distributing* the software; this
runs only as a server-side dependency inside Lingua's own backend and is
never redistributed, so it doesn't require this app's own source to be
released (that's what AGPL is for, and this isn't it) — same reasoning
under which countless SaaS products depend on GPL-licensed CLI tools
(ffmpeg-GPL builds, ImageMagick, etc.) internally without relicensing.

Voice models come from the paired rhasspy/piper-voices dataset on Hugging
Face — a *static file* download (huggingface.co/.../resolve/main/...), not
an Inference Providers API call, so it's unaffected by both of the HF
problems above: it doesn't touch the dead api-inference.huggingface.co host,
and it isn't gated by Inference Providers billing at all.

Downloaded once per language, then cached to disk forever (same pattern as
every other media cache in this app) — voice models are ~20-90MB each, so
this only costs disk space for languages actually requested, never a
repeated download.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import urllib.parse
import wave

import httpx

from .config import settings

logger = logging.getLogger("lingua.piper_tts")

_VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_http = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

# Splits after a sentence-ending punctuation mark followed by whitespace,
# keeping the punctuation attached to the sentence before it. Not a real
# NLP tokenizer (an abbreviation like "Dr." mid-sentence would split early)
# — that's an acceptable tradeoff here, since the only thing this feeds is
# TTS pacing (see hf_client.stream_speech): a slightly-off sentence
# boundary means one audio clip ends a beat early, not a wrong answer.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")


def split_into_sentences(text: str) -> list[str]:
    """Splits `text` into sentence-sized chunks for progressive TTS
    synthesis. Never returns an empty list for non-empty input — a block
    with no sentence-ending punctuation at all comes back as one chunk."""
    text = text.strip()
    if not text:
        return []
    return [s for s in (chunk.strip() for chunk in _SENTENCE_SPLIT_RE.split(text)) if s]

# ISO 639-1 -> best single-speaker Piper voice, picked from rhasspy/piper-
# voices' own voices.json (highest quality among single-speaker voices per
# language, medium preferred over x_low/low for intelligibility, high only
# where no medium single-speaker voice exists). Deliberately narrower than
# hf_client's _MMS_LANG_CODES (53 languages vs. 79) — a language missing
# here just falls through to the existing HF/MMS path in text_to_speech(),
# same as a language missing from MMS falls through to no audio at all.
_PIPER_VOICES: dict[str, str] = {
    "ar": "ar_JO-kareem-medium",
    "bg": "bg_BG-dimitar-medium",
    "bn": "bn_BD-google-medium",
    "ca": "ca_ES-upc_ona-medium",
    "cs": "cs_CZ-jirka-medium",
    "cy": "cy_GB-gwryw_gogleddol-medium",
    "da": "da_DK-talesyntese-medium",
    "de": "de_DE-thorsten-high",
    "el": "el_GR-joy-medium",
    "en": "en_US-lessac-high",
    "es": "es_ES-davefx-medium",
    "eu": "eu_ES-antton-medium",
    "fa": "fa_IR-amir-medium",
    "fi": "fi_FI-harri-medium",
    "fr": "fr_FR-siwis-medium",
    "he": "he_IL-saspeech-medium",
    "hi": "hi_IN-pratham-medium",
    "hu": "hu_HU-anna-medium",
    "hy": "hy_AM-gor-medium",
    "id": "id_ID-news_tts-medium",
    "is": "is_IS-bui-medium",
    "it": "it_IT-paola-medium",
    "ka": "ka_GE-natia-medium",
    "kk": "kk_KZ-iseke-x_low",
    "ko": "ko_KR-kss-medium",
    "lb": "lb_LU-marylux-medium",
    "lv": "lv_LV-aivars-medium",
    "ml": "ml_IN-arjun-medium",
    "ne": "ne_NP-chitwan-medium",
    "nl": "nl_NL-alex-medium",
    "no": "no_NO-talesyntese-medium",
    "pl": "pl_PL-bass-high",
    "pt": "pt_PT-tugão-medium",
    "ro": "ro_RO-mihai-medium",
    "ru": "ru_RU-denis-medium",
    "sk": "sk_SK-lili-medium",
    "sl": "sl_SI-artur-medium",
    "sq": "sq_AL-edon-medium",
    "sv": "sv_SE-alma-medium",
    "sw": "sw_CD-lanfrica-medium",
    "te": "te_IN-maya-medium",
    "tr": "tr_TR-dfki-medium",
    "uk": "uk_UA-mykyta-high",
    "ur": "ur_PK-aegis_female-medium",
    "vi": "vi_VN-vais1000-medium",
    "zh": "zh_CN-chaowen-medium",
}

_voice_cache: dict[str, "PiperVoice"] = {}  # noqa: F821 - forward ref, piper imported lazily
_voice_lock = asyncio.Lock()


def voice_key_for(target_lang: str) -> str | None:
    return _PIPER_VOICES.get(target_lang.lower()[:2])


def _voice_url_prefix(voice_key: str) -> str:
    """rhasspy/piper-voices lays voices out as
    {lang}/{lang_region}/{name}/{quality}/{lang_region}-{name}-{quality}.onnx
    — e.g. "en_US-lessac-high" -> en/en_US/lessac/high/en_US-lessac-high.onnx.
    Every voice_key in _PIPER_VOICES has exactly this 3-part hyphenated shape
    (region/name/quality use underscores internally, never hyphens). Each
    segment is percent-encoded individually — some voice names (e.g.
    "pt_PT-tugão-medium") contain non-ASCII characters."""
    lang_region, name, quality = voice_key.split("-")
    lang = lang_region.split("_")[0]
    segments = [lang, lang_region, name, quality, voice_key]
    return "/".join(urllib.parse.quote(s, safe="") for s in segments)


async def _download_voice_files(voice_key: str) -> tuple[str, str] | None:
    # Lives under audio_store_dir, not cache_dir — a downloaded voice model
    # is a permanent, reusable resource (like the audio it synthesizes),
    # never subject to cache_gc's LRU eviction. Losing one to eviction mid-
    # traffic would force the next request for that language to pay a fresh
    # ~20-90MB download inline, which is exactly the kind of latency spike
    # that breaks a click-triggered play() (see routers/audio.py's docstring).
    url_prefix = _voice_url_prefix(voice_key)
    onnx_path = os.path.join(settings.audio_store_dir, "piper-voices", f"{voice_key}.onnx")
    json_path = os.path.join(settings.audio_store_dir, "piper-voices", f"{voice_key}.onnx.json")
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)

    if os.path.exists(onnx_path) and os.path.exists(json_path):
        return onnx_path, json_path

    try:
        for rel, dest in ((f"{url_prefix}.onnx", onnx_path), (f"{url_prefix}.onnx.json", json_path)):
            if os.path.exists(dest):
                continue
            resp = await _http.get(f"{_VOICES_BASE}/{rel}")
            if resp.status_code != 200:
                logger.warning("Piper voice download HTTP %s for %s", resp.status_code, rel)
                return None
            tmp_dest = f"{dest}.part"
            with open(tmp_dest, "wb") as f:
                f.write(resp.content)
            os.replace(tmp_dest, dest)
    except Exception:
        logger.exception("Piper voice download failed for %s", voice_key)
        return None
    return onnx_path, json_path


async def _load_voice(voice_key: str):
    if voice_key in _voice_cache:
        return _voice_cache[voice_key]

    async with _voice_lock:
        if voice_key in _voice_cache:  # re-check after acquiring the lock
            return _voice_cache[voice_key]

        paths = await _download_voice_files(voice_key)
        if paths is None:
            return None
        onnx_path, json_path = paths

        try:
            from piper import PiperVoice  # imported lazily: heavy (onnxruntime), optional dependency

            voice = await asyncio.to_thread(PiperVoice.load, onnx_path, json_path)
        except Exception:
            logger.exception("Piper voice load failed for %s", voice_key)
            return None

        _voice_cache[voice_key] = voice
        return voice


def _synthesize_sync(voice, text: str) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    return buf.getvalue()


async def synthesize(text: str, target_lang: str) -> bytes | None:
    """Returns WAV audio bytes for `text` in the given target language, or
    None if Piper has no voice for that language or synthesis genuinely
    fails — callers (hf_client.text_to_speech) fall back to Hugging Face's
    MMS-TTS path in either case, so this never needs to raise."""
    voice_key = voice_key_for(target_lang)
    if voice_key is None:
        return None

    voice = await _load_voice(voice_key)
    if voice is None:
        return None

    try:
        return await asyncio.to_thread(_synthesize_sync, voice, text)
    except Exception:
        logger.exception("Piper synthesis failed for voice=%s", voice_key)
        return None
