"""Settings for the Lingua language-learning app — fully independent from apps/core.

Reads from the environment (or a local .env in language-app/) so this app can be
deployed and run without any dependency on ARIA's own settings module.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent

# Generated once per process if LINGUA_SESSION_SECRET isn't set. Sessions won't
# survive a restart or work across multiple instances in that case — fine for
# local dev, not for a real multi-machine deploy (set the env var there).
_EPHEMERAL_SESSION_SECRET = secrets.token_hex(32)


def _load_dotenv() -> None:
    env_path = _BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Hugging Face is now the *secondary* provider: an automatic fallback for
    # chat if Pollinations' anonymous budget is exhausted (see chat() in
    # hf_client.py), plus the only option this app has for TTS, speech-to-
    # text, and video generation. Needs a paid Inference Providers plan or
    # credits — which this deployment's account has exhausted — and even
    # with credits, Hugging Face retired the old api-inference.huggingface.co
    # host, so the endpoint below is the current unified router.
    hf_token: str = field(default_factory=lambda: os.environ.get("HF_TOKEN", "") or os.environ.get("HF_API_KEY", ""))
    hf_chat_model: str = field(
        default_factory=lambda: os.environ.get("LINGUA_HF_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    )
    stt_model: str = field(default_factory=lambda: os.environ.get("LINGUA_STT_MODEL", "openai/whisper-large-v3"))
    tts_model_prefix: str = field(
        default_factory=lambda: os.environ.get("LINGUA_TTS_MODEL_PREFIX", "facebook/mms-tts")
    )
    # Text-to-video has much narrower serverless Inference API support than
    # text/image/audio — this is the model most commonly available there.
    # Best-effort by design: a slow or unavailable model degrades to "video
    # unavailable" rather than breaking the request.
    video_model: str = field(
        default_factory=lambda: os.environ.get("LINGUA_VIDEO_MODEL", "damo-vilab/text-to-video-ms-1.7b")
    )
    hf_chat_endpoint: str = "https://router.huggingface.co/v1/chat/completions"
    hf_models_endpoint: str = "https://router.huggingface.co/hf-inference/models"

    # ── Pollinations.ai — primary provider for chat and images ──────────
    # Free, keyless, no signup, no billing. Image generation (Flux) is
    # confirmed solid and effectively unlimited. Chat's anonymous tier works
    # but has a small, easily-exhausted per-source request budget (confirmed
    # directly: the first call succeeded, the next got HTTP 402 "budget too
    # low") — chat() falls back to Hugging Face when that happens, see
    # above. Pollinations no longer offers keyless TTS (their audio endpoint
    # now requires a paid API key), so text_to_speech() stays on the
    # Hugging Face path only. An optional token (POLLINATIONS_API_TOKEN)
    # raises the chat/image rate limit but nothing here requires one.
    pollinations_token: str = field(default_factory=lambda: os.environ.get("POLLINATIONS_API_TOKEN", ""))
    pollinations_chat_endpoint: str = "https://text.pollinations.ai/openai"
    pollinations_image_endpoint: str = "https://image.pollinations.ai/prompt"
    chat_model: str = field(default_factory=lambda: os.environ.get("LINGUA_CHAT_MODEL", "openai"))
    image_model: str = field(default_factory=lambda: os.environ.get("LINGUA_IMAGE_MODEL", "flux"))

    # Set by tests/conftest.py so the suite stays fully offline and
    # deterministic — Pollinations needs no token, so without this flag
    # every AI call in the test run would be a real network request instead
    # of hitting the fallback content the tests assert on.
    testing: bool = field(default_factory=lambda: os.environ.get("LINGUA_TESTING", "") == "1")

    db_path: str = field(default_factory=lambda: os.environ.get("LINGUA_DB_PATH", str(_BASE_DIR / "data" / "lingua.db")))
    cache_dir: str = field(default_factory=lambda: os.environ.get("LINGUA_CACHE_DIR", str(_BASE_DIR / "data" / "media_cache")))

    # Durable production storage: a dedicated Supabase Postgres project (never
    # ARIA's). When set, db.py persists users/progress/sessions-linked state
    # here instead of the local SQLite file, so a Fly restart or redeploy never
    # loses data. When unset (local dev, tests), db.py falls back to SQLite —
    # fully offline, zero external dependency, exactly as before.
    supabase_db_url: str = field(
        default_factory=lambda: os.environ.get("SUPABASE_DB_URL", "") or os.environ.get("DATABASE_URL", "")
    )

    host: str = field(default_factory=lambda: os.environ.get("LINGUA_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("LINGUA_PORT", "8100")))

    request_timeout_s: float = 60.0

    # ── Google Sign-In ───────────────────────────────────────────────────
    # A dedicated OAuth client for Lingua — deliberately not shared with
    # ARIA's own Google OAuth client/credentials. Register the redirect URI
    # printed by `python -m backend.main` (or see README.md) in this client.
    google_client_id: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLIENT_SECRET", ""))

    # ── Google Image Search (vocabulary flashcards) ─────────────────────
    # A simpler, free alternative to AI image generation: real photos via
    # Google's Custom Search JSON API (free up to 100 queries/day). Fully
    # optional — see image_search.py and README.md for one-time setup. When
    # unset, the app falls back to the existing FLUX.1-schnell generation.
    google_cse_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_CSE_API_KEY", ""))
    google_cse_cx: str = field(default_factory=lambda: os.environ.get("GOOGLE_CSE_CX", ""))

    # Public origin this app is served from — drives the OAuth redirect_uri.
    # Defaults to the Fly domain declared in fly.toml; override for local dev
    # (e.g. http://localhost:8100) or a custom domain.
    public_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "LINGUA_PUBLIC_BASE_URL", f"http://localhost:{os.environ.get('LINGUA_PORT', '8100')}"
        ).rstrip("/")
    )

    session_secret: str = field(
        default_factory=lambda: os.environ.get("LINGUA_SESSION_SECRET", "") or _EPHEMERAL_SESSION_SECRET
    )

    # Lets you sign in locally/in tests without real Google credentials —
    # mirrors this app's "runs without HF_TOKEN too" demo-mode philosophy.
    # Auto-disabled the moment real Google credentials are configured, unless
    # explicitly re-enabled (a real deploy shouldn't ship an auth bypass by
    # accident).
    _dev_login_override: str = field(default_factory=lambda: os.environ.get("LINGUA_ALLOW_DEV_LOGIN", ""))

    @property
    def hf_configured(self) -> bool:
        return bool(self.hf_token)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_images_configured(self) -> bool:
        return bool(self.google_cse_api_key and self.google_cse_cx)

    @property
    def cookie_secure(self) -> bool:
        return self.public_base_url.startswith("https://")

    @property
    def dev_login_enabled(self) -> bool:
        if self._dev_login_override:
            return self._dev_login_override == "1"
        return not self.google_configured


settings = Settings()
