"""Security response headers — the FastAPI/Starlette equivalent of Express's
Helmet middleware. Applied to every response via main.py's app.middleware.

The CSP is scoped to what this app actually loads: same-origin scripts only
(no inline <script>, no third-party JS), Google Fonts for style/font-src,
'unsafe-inline' for style-src only (a handful of dynamic inline `style=`
attributes for per-item accent colors — a CSS-injection risk, not a script
one, and low severity now that every AI-generated string rendered via
innerHTML is HTML-escaped, see escapeHtml() in frontend/app.js), and
data:/blob: for images and audio (TTS playback uses blob: object URLs)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=(), payment=()"
        # HSTS only makes sense once we're actually reachable over HTTPS —
        # sending it against a local http:// dev server would be inert but
        # misleading; gate it the same way cookie_secure already does.
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
