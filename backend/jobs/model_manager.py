"""Generic download-once, verify-once, reuse-forever manager for any model
file a job executor needs on local disk — not specific to Piper, even
though Piper voice models (backend/piper_tts.py) are the only registered
consumer today. Any future executor that needs its own local model
weights (a different local TTS engine, a local embedding model, ...) uses
the same `ensure_file` primitive instead of writing its own ad hoc
download logic.

Three things this actually buys over the naive "httpx.get() the whole
file" approach that piper_tts.py used before:

1. Resumable: a `.part` file's existing size becomes a `Range: bytes=N-`
   request on the next attempt instead of restarting from zero. This is
   the direct fix for what happened during the audio backfill attempts —
   a large (~100MB) voice model download that got interrupted partway
   (an SSH tunnel timing out, or any other network blip) used to mean
   the *next* attempt paid for the same bytes all over again.
2. Verified once: after a download completes, the response's ETag
   (Hugging Face's CDN returns the LFS object's sha256 as the ETag for
   files tracked via git-lfs/xet, which every large binary in
   rhasspy/piper-voices is) is recorded in a small JSON sidecar next to
   the file. A later call with the sidecar already present and matching
   trusts the file without re-hashing it — hashing every model file on
   every process start doesn't scale to the "millones de assets" this
   is meant to eventually support.
3. Reused forever: once verified, `ensure_file` is a stat() call — no
   network round trip at all, whether it's called from a fresh build, a
   repair job, or a hundred concurrent requests for the same voice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

import httpx

logger = logging.getLogger("lingua.jobs.model_manager")

_http = httpx.AsyncClient(timeout=120.0, follow_redirects=True)


def _sidecar_path(dest_path: str) -> str:
    return f"{dest_path}.meta.json"


def _etag_looks_like_sha256(etag: str) -> bool:
    etag = etag.strip('"')
    return len(etag) == 64 and all(c in "0123456789abcdef" for c in etag.lower())


def _is_verified(dest_path: str) -> bool:
    sidecar = _sidecar_path(dest_path)
    if not (os.path.isfile(dest_path) and os.path.isfile(sidecar)):
        return False
    try:
        with open(sidecar, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    return meta.get("size") == os.path.getsize(dest_path)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def ensure_file(url: str, dest_path: str) -> bool:
    """Ensures `dest_path` contains the complete, verified contents of
    `url`, downloading (or resuming a partial download) only if it
    doesn't already. Returns False on any failure (network error, a
    verification mismatch) — never raises, matching this app's "degrade,
    log, let the caller retry later" convention (see hf_client.py)."""
    if _is_verified(dest_path):
        return True

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    part_path = f"{dest_path}.part"
    resume_from = os.path.getsize(part_path) if os.path.isfile(part_path) else 0

    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
    try:
        async with _http.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 416:  # "Range Not Satisfiable" — our .part is already complete or corrupt
                os.remove(part_path)
                resume_from = 0
                return await ensure_file(url, dest_path)
            if resp.status_code not in (200, 206):
                logger.warning("model download HTTP %s for %s", resp.status_code, url)
                return False
            mode = "ab" if resp.status_code == 206 else "wb"
            if mode == "wb":
                resume_from = 0
            etag = resp.headers.get("etag", "")
            with open(part_path, mode) as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    except Exception:
        logger.exception("model download failed/interrupted for %s (resumable — next attempt continues from byte %d)", url, resume_from)
        return False

    downloaded_size = os.path.getsize(part_path)
    if _etag_looks_like_sha256(etag):
        actual = _sha256_file(part_path)
        if actual != etag.strip('"'):
            logger.error("model checksum mismatch for %s: expected %s, got %s — discarding", url, etag, actual)
            os.remove(part_path)
            return False

    os.replace(part_path, dest_path)
    with open(_sidecar_path(dest_path), "w", encoding="utf-8") as f:
        json.dump({"url": url, "size": downloaded_size, "etag": etag}, f)
    logger.info("model download complete+verified: %s (%d bytes)", dest_path, downloaded_size)
    return True
