# Lingua — AI Language Coach

A standalone language-learning app in its own repository — no shared code,
database, domain, or deployment with the ARIA project it originated
alongside (see [Independence from ARIA](#independence-from-aria) below).

Lingua teaches any language, beginner to native speaker, blending two proven
methodologies:

- **Duolingo-style** gamified skill tree, spaced repetition, XP, streaks, hearts,
  a gem economy (earn-only — no real-money purchases, ever), auto-consuming
  streak freezes, and a weekly leaderboard ranking every learner by XP.
- **Rosetta Stone-style** immersion: early lessons teach meaning through images
  and audio only, with translations introduced gradually as the learner advances.
- **Adaptive placement test** at onboarding (`backend/routers/placement.py`) —
  a short staircase test (start medium, harder after correct, easier after a
  miss, same mechanic Duolingo's own placement test uses) picks the learner's
  starting level instead of asking them to self-report it from a dropdown.
- **50+ languages** in the picker (`frontend/app.js` `LANGS`), each mapped to
  an MMS-TTS voice (`backend/hf_client.py` `_MMS_LANG_CODES`) — exercise/chat
  generation itself is language-agnostic and works with any language the chat
  model knows, so a language missing a TTS mapping still teaches fully via
  text, just without narrated audio.

On top of that, AI powers three things static courses can't do:

1. **Personalized exercises** — generated per lesson from the learner's level,
   native/target language pair, stated interests, and recent mistakes, instead
   of one fixed script for everyone.
2. **Real audio and images** — text-to-speech per phrase and generated
   illustrations per vocabulary item.
3. **Live spoken conversation practice** ("Talk Live") — push-to-talk voice
   chat with an AI tutor: your speech is transcribed, the model replies in the
   target language at your level (with gentle corrections), and the reply is
   spoken back to you while an avatar animates — the practical equivalent of
   a video-call conversation partner, without requiring full video generation.

## Architecture

```
backend/
  main.py          FastAPI app + static frontend mount
  config.py         env-based settings (Pollinations, HF_TOKEN, Google OAuth, Supabase, model IDs, ports)
  auth.py              Google Sign-In + signed session/state cookies (no server-side store)
  models.py          Pydantic/enum domain models (CEFR levels, exercise types)
  db.py               Persistence: Supabase Postgres in production, SQLite fallback locally/in tests
  curriculum.py    language-agnostic skill tree + HF prompt templates
  srs.py               SM-2 spaced repetition + XP/streak/leveling logic
  hf_client.py      AI client: chat + text-to-image on Pollinations.ai (free, keyless), TTS/STT/video on Hugging Face (optional)
  routers/             auth, users, lessons, content (media), progress, conversation (WebSocket)
frontend/            vanilla HTML/CSS/JS SPA — no build step
tests/                  pytest suite (SRS, curriculum, auth, and full API flow)
fly.toml, Dockerfile     deploy config for Lingua's own Fly.io app/domain
.github/workflows/    CI (tests) + deploy-to-Fly, both scoped to this repo only
```

### Why Supabase, and why it's still safe to test offline

Sessions/user data need to survive a Fly restart or redeploy, so production
storage is a dedicated Supabase Postgres project — never ARIA's, never
shared. `db.py` picks the backend automatically: when `SUPABASE_DB_URL` is
set it talks to Postgres; when it isn't (local dev without a Supabase
project, and the entire test suite) it transparently falls back to a local
SQLite file, so nothing external is required to run or test the app. If a
configured Supabase connection ever fails at startup, the app logs the error
and falls back to SQLite for that process rather than crashing — see
[Supabase setup](#supabase-setup) below for the exact grants a production
database role needs.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Chat and image generation run on [Pollinations.ai](https://pollinations.ai) —
free and keyless, no setup required. `HF_TOKEN` is optional: it only enables
text-to-speech, speech-to-text, and video generation, plus a chat fallback for
when Pollinations' small anonymous request budget is exhausted. Get one at
https://huggingface.co/settings/tokens (read access is enough) if you want
those.

### Google Sign-In setup

Create a dedicated OAuth client for this app:

1. https://console.cloud.google.com/apis/credentials → **Create Credentials**
   → **OAuth client ID** → Application type **Web application**.
2. Under **Authorized redirect URIs**, add:

   ```
   https://language-ai-x90j9w.fly.dev/auth/google/callback
   ```

   That's the exact value to register — it comes from the domain in
   `fly.toml` (see [Domain & deployment](#domain--deployment) below). If you
   deploy under a different Fly app name or a custom domain, use
   `https://<your-domain>/auth/google/callback` instead.

   Also add this one so sign-in works from a local dev server too:

   ```
   http://localhost:8100/auth/google/callback
   ```

3. Copy the generated **Client ID** and **Client secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```
4. Generate a session secret (required for sessions to survive a restart /
   work across more than one instance) and add it too:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

Without `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` set, the app automatically
falls back to a `/auth/dev-login?email=you@example.com` endpoint so you can
still sign in locally (and so the test suite doesn't need real Google
credentials). That fallback disables itself the moment real Google
credentials are configured, unless you explicitly opt back in with
`LINGUA_ALLOW_DEV_LOGIN=1` — a real deployment should never ship that on by
accident.

### Supabase setup

1. Create a project at https://supabase.com/dashboard (own org, not shared
   with any other product).
2. Don't use the `postgres` superuser for the app — Supabase blocks
   `ALTER ROLE postgres` outright, and reusing a superuser is bad practice
   anyway. Create a dedicated low-privilege role instead, in the SQL Editor:

   ```sql
   CREATE ROLE lingua_app WITH LOGIN PASSWORD 'a-strong-password'
     NOSUPERUSER NOCREATEDB NOCREATEROLE;

   GRANT USAGE, CREATE ON SCHEMA public TO lingua_app;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO lingua_app;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO lingua_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO lingua_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO lingua_app;

   -- If tables already exist (created by another role), the app also needs
   -- to own them to run its own migrations (CREATE INDEX/ALTER TABLE need
   -- ownership, not just row-level privileges):
   GRANT lingua_app TO postgres; -- lets postgres reassign ownership below
   ALTER TABLE users OWNER TO lingua_app;
   ALTER TABLE vocab_progress OWNER TO lingua_app;
   ALTER TABLE lesson_history OWNER TO lingua_app;
   ALTER TABLE unit_mastery OWNER TO lingua_app;
   ALTER TABLE conversation_log OWNER TO lingua_app;
   ```

   `backend/db.py` creates these 5 tables itself on first connect (same
   `CREATE TABLE IF NOT EXISTS` schema either way), so you don't need to
   run the schema by hand — just the role + grants above.
3. Build the connection string (Session pooler mode — IPv4, suited to a
   single persistent backend process like this app's):

   ```
   postgresql://lingua_app.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

   Find `<project-ref>` and `<region>` on the project's dashboard, or under
   Settings → Database → Connection string (pick "Session pooler").
4. Set it as `SUPABASE_DB_URL` in `.env` locally, or as a Fly/GitHub secret
   in production (see [Domain & deployment](#domain--deployment)).

### Run

```bash
uvicorn backend.main:app --reload --port 8100
# or: python -m backend.main
```

Then open http://localhost:8100/.

Chat and images (personalized exercises, tutor conversation, vocabulary
illustrations) work out of the box via Pollinations — no token needed.
Without `HF_TOKEN` set, there's just no text-to-speech, speech-to-text, or
video generation, and chat has no fallback if Pollinations' free tier is
temporarily exhausted (the app degrades gracefully to offline template
content in that case, never a broken request). Set `HF_TOKEN` for those
extras.

### Test

```bash
pytest
```

The test suite (SRS scheduling, curriculum/prompt logic, auth signing, and a
full onboarding→lesson→progress API flow) runs entirely offline against an
isolated temp SQLite file per test — no real network calls, no shared state
with dev data (`LINGUA_TESTING=1`, set automatically by `tests/conftest.py`,
short-circuits every AI call before it reaches the network).

## Models used (overridable via env vars)

| Purpose                             | Provider                    | Default model                       |
|--------------------------------------|------------------------------|---------------------------------------|
| Exercise generation / tutor chat     | Pollinations (HF fallback)  | `openai` (Pollinations) / `Qwen/Qwen2.5-7B-Instruct` (HF) |
| Vocabulary illustrations             | Pollinations                 | `flux`                               |
| Speech-to-text (conversation mode)   | Hugging Face (optional)     | `openai/whisper-large-v3`           |
| Text-to-speech                       | Hugging Face (optional)     | `facebook/mms-tts-<lang>` (per target language) |
| Academy topic videos                 | Hugging Face (optional)     | `damo-vilab/text-to-video-ms-1.7b`  |

Chat and images run on Pollinations.ai — free, keyless, no signup. Chat falls
back to Hugging Face (if `HF_TOKEN` is set) when Pollinations' small
anonymous request budget is temporarily exhausted. TTS, speech-to-text, and
video generation stay on the optional Hugging Face path: Pollinations'
image generation is solid and free, but it no longer offers keyless
transcription or audio (its old free audio endpoint now requires a paid
`enter.pollinations.ai` API key), so those three features simply aren't
available without `HF_TOKEN` — gracefully, not as a broken request.

### Vocabulary flashcard images: free Google Image Search (optional)

By default, flashcard images come from AI generation (FLUX.1-schnell above).
`backend/image_search.py` adds a simpler, cheaper alternative — real photos
via Google's Custom Search JSON API, free up to 100 queries/day — tried
first when configured, with AI generation as the automatic fallback:

1. Create a search engine at https://programmablesearchengine.google.com/
   with "Search the entire web" and "Image search" turned on, and copy its
   Search engine ID.
2. Create an API key with the "Custom Search API" enabled at
   https://console.cloud.google.com/apis/credentials.
3. Set `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_CX`.

Leave both unset to keep using AI-generated images only — nothing else
changes.

## How personalization actually works

- **Curriculum** (`curriculum.py`) defines a language-agnostic topic/skill
  tree across CEFR levels A1→C2 plus a "native polish" tier. The *content* for
  each topic is generated on demand by the chat model for the learner's
  specific language pair — so one curriculum serves every language, rather
  than hand-authored word lists per language.
- **Interests** the learner enters at onboarding are woven into example
  sentences and conversation small talk.
- **Mistakes** are tracked per vocabulary item (`vocab_progress` table, SM-2
  scheduling in `srs.py`); recently-missed items are surfaced both as spaced
  review and as material the next lesson's prompt explicitly re-practices.
- **Level-appropriate immersion**: A1 lessons never show a translation (image
  + audio + target text only, Rosetta Stone-style); translations appear from
  A2; free-form conversation exercises unlock at B1.

## Domain & deployment

Lingua deploys to its own Fly.io app/domain:

- `fly.toml` declares app `language-ai-x90j9w` → **`language-ai-x90j9w.fly.dev`**.
- `Dockerfile` is a standalone image built from this repo.
- `.github/workflows/deploy.yml` deploys on every push to `main`, gated on
  `.github/workflows/ci.yml` passing first, using the `FLY_API_TOKEN` repo secret.

To ship it the first time:

```bash
fly volumes create lingua_data --size 1 --region ord --app language-ai-x90j9w
fly secrets set \
  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... LINGUA_SESSION_SECRET=... \
  SUPABASE_DB_URL=... \
  --app language-ai-x90j9w
# HF_TOKEN is optional — only needed for TTS/STT/video and the chat fallback
fly deploy --app language-ai-x90j9w --remote-only
```

If you rename the Fly app or bring your own domain, update **both**
`LINGUA_PUBLIC_BASE_URL` (in `fly.toml`/secrets) **and** the redirect URI
registered in Google Cloud Console to match — they must always agree.

For CI-driven deploys, set these repo secrets (Settings → Secrets and
variables → Actions): `FLY_API_TOKEN`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`, `LINGUA_SESSION_SECRET`, `SUPABASE_DB_URL`, and
optionally `HF_TOKEN`.

## Independence from ARIA

This app started life as a prototype inside ARIA's monorepo and has since
moved into this dedicated repository. Nothing is shared going forward:

- Own repo, own git history, own issues/PRs/CI.
- Own Supabase project and database role (local dev/tests still need
  nothing but SQLite — see [Supabase setup](#supabase-setup)).
- Own FastAPI app and static frontend.
- Own Google OAuth client, own session cookies/secret, own domain (see
  [Domain & deployment](#domain--deployment)) — none of it shared with ARIA's
  own Google login or `aria-ai.fly.dev` deployment.
- Runs on its own port (`8100` by default) and deploys independently of
  ARIA's Docker/Fly/Vercel setup.
