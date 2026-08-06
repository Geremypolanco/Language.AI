"""Serves permanently-cached, content-addressed synthesized speech (see
backend/hf_client.py's text_to_speech/_audio_cache_path and
backend/config.py's audio_store_dir).

A filename here is sha256(provider-tier + voice/persona + text)-derived, so
its bytes never change once written — safe to cache forever, in the
browser or in any CDN placed in front of this app. That is the single
concrete fix for the "the button appears but the audio never plays" bug:
the old /api/content/tts POST returned raw bytes with no cache headers to
a JS blob: URL, and the actual HTMLMediaElement.play() call happened in a
React effect one tick after that fetch resolved — on a slow/cold
synthesis, the browser's user-activation window from the original click
had often already expired by the time play() ran, and the failure was
swallowed by an empty .catch(). Serving a real, stable GET URL instead
lets the <audio> element's own native loading/buffering handle it, and
(FastAPI/Starlette's FileResponse) gives Range support for free — no
custom streaming code needed for a browser to seek or make a partial
request.

Public/unauthenticated on purpose: filenames are unguessable hashes of
already-public lesson content, not user data, so there is nothing here an
auth check would protect."""

from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import settings

logger = logging.getLogger("lingua.routers.audio")

router = APIRouter(prefix="/api/audio", tags=["audio"])

# Every filename this app ever writes under audio_store_dir is
# "<namespace>-<32 hex chars>.<ext>" (see hf_client._audio_cache_path) —
# reject anything else outright rather than letting a crafted path
# component reach os.path.join/isfile.
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.(wav|flac|mp3)$")
_MEDIA_TYPES = {"wav": "audio/wav", "flac": "audio/flac", "mp3": "audio/mpeg"}

# Content-addressed and immutable: the same filename can never later refer
# to different bytes, so a year-long cache lifetime (browser or CDN) is
# safe, unlike a normal URL whose content might change server-side.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get("/{filename}")
async def get_audio(filename: str) -> FileResponse:
    if not _FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Nombre de archivo de audio inválido")
    path = os.path.join(settings.audio_store_dir, filename)
    if not os.path.isfile(path):
        logger.warning("audio miss filename=%s (not found under audio_store_dir)", filename)
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    ext = filename.rsplit(".", 1)[1]
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[ext],
        headers={"Cache-Control": _CACHE_CONTROL},
    )
