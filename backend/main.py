"""Lingua — a standalone AI language-learning app (separate product from ARIA).

Combines Duolingo's gamified, adaptive skill-tree methodology with Rosetta
Stone's image/audio immersion approach, powered by Hugging Face models for
personalized exercise generation, illustrations, speech, and live spoken
conversation practice.

Run directly with:  python -m backend.main   (from language-app/)
or:                  uvicorn backend.main:app --reload --port 8100
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache_gc import run_periodic_gc
from .config import settings
from .hf_client import hf_client
from .routers import auth as auth_router
from .routers import academy, content, conversation, feedback, lessons, library, placement, progress, shop, users
from .security_headers import SecurityHeadersMiddleware

logger = logging.getLogger("lingua.main")

_PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
_TEAM_AVATARS_DIR = _PUBLIC_DIR / "team"
# Built by the Docker frontend-builder stage (see Dockerfile); absent in
# CI/tests, which don't run the frontend build — the app must not crash
# when it's missing, just skip serving a root page (see below).
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    redirect_uri = f"{settings.public_base_url}/auth/google/callback"
    if settings.google_configured:
        logger.info("Google Sign-In enabled. Redirect URI: %s", redirect_uri)
    else:
        logger.warning(
            "Google Sign-In not configured (GOOGLE_CLIENT_ID/SECRET unset). "
            "Register this exact redirect URI in Google Cloud Console once you set them: %s "
            "— dev-login fallback is %s.",
            redirect_uri,
            "enabled" if settings.dev_login_enabled else "disabled",
        )

    # Keeps the disk cache under budget for as long as the app runs — see
    # cache_gc.py. Skipped in tests: it's a disk-scanning background loop
    # with nothing to do against the tests' throwaway cache dir, and no
    # test asserts on it.
    gc_task = None if settings.testing else asyncio.create_task(run_periodic_gc())

    yield

    if gc_task is not None:
        gc_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await gc_task
    await hf_client.aclose()


app = FastAPI(title="Lingua — AI Language Coach", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(lessons.router)
app.include_router(content.router)
app.include_router(progress.router)
app.include_router(shop.router)
app.include_router(placement.router)
app.include_router(conversation.router)
app.include_router(library.router)
app.include_router(academy.router)
app.include_router(feedback.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "hf_configured": settings.hf_configured,
        "google_configured": settings.google_configured,
    }


# Static asset mounting
if _PUBLIC_DIR.exists():
    # Mount /public for all root assets (logos, avatars, heroes)
    app.mount("/public", StaticFiles(directory=str(_PUBLIC_DIR)), name="public")
    
    # Backward compatibility for /team/ paths
    if _TEAM_AVATARS_DIR.exists():
        app.mount("/team", StaticFiles(directory=str(_TEAM_AVATARS_DIR)), name="team-avatars")

# Serve React frontend (built from Vite)
if _FRONTEND_DIST.exists():
    # Mount frontend assets
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="frontend-assets")
    
    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{path:path}")
    async def serve_spa(path: str) -> FileResponse:
        # If it's an API route, let FastAPI handle it
        if path.startswith(("api/", "auth/", "public/", "team/")):
            raise HTTPException(status_code=404)
        # Otherwise serve the React app
        return FileResponse(str(_FRONTEND_DIST / "index.html"))


def main() -> None:
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
