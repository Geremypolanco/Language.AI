"""Rate limiting for the routes that trigger a paid HF Inference call (chat
generation, image, TTS, STT) — protects the HF_TOKEN's quota from being
burned by a runaway client or script, not a general API gate.

No Redis: this app deploys a single Fly machine (`min_machines_running = 1`
in fly.toml), so a plain in-process sliding-window counter is both correct
(no cross-instance state to reconcile) and one less piece of infrastructure
to run and pay for. If this ever moves to multiple machines, the counter
would need to move to something shared (Postgres, since Supabase is already
configured, or Redis) — noted here rather than built speculatively now.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import auth
from .config import settings

# Any path matching one of these has already reached the HF Inference API
# by the time a 200 comes back — these are the ones worth metering.
_AI_ROUTE_PATTERNS = (
    re.compile(r"^/api/content/(tts|image|stt|tutor-reply|recommendations)$"),
    re.compile(r"^/api/lessons/[^/]+/unit/"),
    re.compile(r"^/api/lessons/[^/]+/practice$"),
    re.compile(r"^/api/library/[^/]+/books/"),
    re.compile(r"^/api/academy/[^/]+/curriculum$"),
    re.compile(r"^/api/academy/[^/]+/courses/"),
)

_WINDOW_SECONDS = 60.0


def _is_ai_route(path: str) -> bool:
    return any(p.match(path) for p in _AI_ROUTE_PATTERNS)


class _SlidingWindowCounter:
    """Per-identifier request timestamps, pruned to the current window on
    every check. Fine at this app's scale (one process, one machine) —
    would need a shared store behind more than one worker/machine."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def hit(self, key: str, limit: int, window: float = _WINDOW_SECONDS) -> tuple[bool, float]:
        now = time.monotonic()
        cutoff = now - window
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= limit:
            retry_after = window - (now - bucket[0])
            return False, max(1.0, retry_after)
        bucket.append(now)
        return True, 0.0


_counter = _SlidingWindowCounter()


def _client_identity(request: Request) -> str:
    """Authenticated user_id when signed in (matches the "per authenticated
    user" half of the requirement) — falls back to client IP for anonymous
    calls (there aren't many; almost every AI route requires a session)."""
    session = auth.get_session(request)
    if session:
        return f"user:{session['user_id']}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _is_ai_route(request.url.path):
            return await call_next(request)

        identity = _client_identity(request)
        allowed, retry_after = _counter.hit(identity, settings.ai_rate_limit_per_minute)
        if not allowed:
            retry_seconds = int(retry_after) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Demasiadas solicitudes de IA. Espera {retry_seconds} segundos e inténtalo de nuevo.",
                    "retry_after_seconds": retry_seconds,
                },
                headers={"Retry-After": str(retry_seconds)},
            )
        return await call_next(request)
