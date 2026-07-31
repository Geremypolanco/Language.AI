# Language AI — AI Language & Academy Coach

A standalone language-learning and accelerated-study app in its own
repository — no shared code, database, domain, or deployment with the ARIA
project it originated alongside (see
[Independence from ARIA](#independence-from-aria) below). Internally the
codebase still refers to itself as "Lingua" in a few places (Python package
docstrings, the Fly app domain, log messages) — only the brand shown to
learners has changed to Language AI; renaming those internals is a separate,
lower-priority cleanup.

Language AI teaches any language, beginner to native speaker, blending two
proven methodologies:

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

On top of that, a Hugging Face model powers three things static courses can't do:

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
  config.py         env-based settings (HF_TOKEN, Google OAuth, Supabase, model IDs, ports)
  auth.py              Google Sign-In + signed session/state cookies (no server-side store)
  models.py          Pydantic/enum domain models (CEFR levels, exercise types)
  db.py               Persistence: Supabase Postgres in production, SQLite fallback locally/in tests
  curriculum.py    language-agnostic skill tree + HF prompt templates
  srs.py               SM-2 spaced repetition + XP/streak/leveling logic
  hf_client.py      HF Inference API wrapper: chat, text-to-image, TTS, STT, embeddings
  academy.py          university-prep field/curriculum definitions + prompts
  oer/                     Open Educational Resources retrieval pipeline (see below)
  routers/             auth, users, lessons, content (media), progress, conversation (WebSocket), academy
scripts/
  ingest_oer.py     admin CLI to populate the OER vector store
frontend/            vanilla HTML/CSS/JS SPA — no build step
tests/                  pytest suite (SRS, curriculum, auth, OER pipeline, and full API flow)
fly.toml, Dockerfile     deploy config for this app's own Fly.io app/domain
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
cp .env.example .env   # then add your HF_TOKEN
```

Get a Hugging Face token at https://huggingface.co/settings/tokens (read
access is enough — it's used against the free-tier serverless Inference API /
Inference Providers).

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

Without `HF_TOKEN` set, the app still runs in **demo mode**: the skill tree,
gamification, and lesson flow all work end-to-end, but exercises use
placeholder template text and there's no audio/image/voice generation. Set
`HF_TOKEN` for the real, personalized experience.

### Test

```bash
pytest
```

The test suite (SRS scheduling, curriculum/prompt logic, auth signing, and a
full onboarding→lesson→progress API flow) runs entirely offline against an
isolated temp SQLite file per test — no HF network calls, no shared state
with dev data.

## Models used (all via Hugging Face Inference API, overridable via env vars)

| Purpose                          | Default model                       |
|-----------------------------------|--------------------------------------|
| Exercise generation / tutor chat  | `Qwen/Qwen2.5-7B-Instruct`           |
| Vocabulary illustrations          | `black-forest-labs/FLUX.1-schnell`  |
| Speech-to-text (conversation mode)| `openai/whisper-large-v3`           |
| Text-to-speech                    | `facebook/mms-tts-<lang>` (per target language) |

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

## Grounding Academy content in real Open Educational Resources (OER)

The Academy tab (`backend/academy.py`) generates accelerated, self-paced
study tracks — Associate, Bachelor, Master, or Doctorate depth — across
~30 fields. Left to itself, the chat model would generate course content
purely from its own training data. `backend/oer/` grounds that generation
in real, citable material instead, following the public REA/OER (Open
Educational Resources) movement: syllabi/skills taxonomies, textbook-level
theory, and practical problem sets, vectorized and retrieved per course.

```
backend/oer/
  sources.py       fetch_arxiv (live arXiv API), load_local_folder (OpenStax/
                    MIT OCW/OER Commons/HF-dataset dumps you download and
                    drop under data/oer_raw/), load_seed_dataset (curated
                    ESCO/O*NET/Kaggle-UCI samples, see seed_data/)
  chunking.py      paragraph-aware text splitter (no LangChain/LlamaIndex
                    dependency — the app doesn't otherwise need one)
  embeddings.py    delegates to HFClient.embed_texts — HF Inference API
                    (sentence-transformers/all-MiniLM-L6-v2 by default), same
                    "no local model install" pattern as chat/image/TTS/STT
  vectorstore.py   persisted ChromaDB collection (data/oer_chroma/);
                    embeddings are always supplied explicitly, so Chroma's
                    own (heavier) default embedding function is never loaded
  retrieval.py     retrieve_context(query, field_id) -> grounded excerpts
  ingest.py        fetch -> chunk -> embed -> upsert orchestration
scripts/ingest_oer.py   admin CLI that drives ingest.py from the command line
```

`hf_client.generate_course_content` retrieves up to 4 relevant chunks for
the course's field before generating, folds them into the prompt as
grounding the model should prefer over invented specifics, and returns
them as `CourseContent.sources` — shown in the UI under each course as
"Contenido basado en fuentes educativas abiertas reales".

### Populating the vector store

Ingestion is a separate, offline step — it never runs on a user's request:

```bash
# Curated seed samples (ESCO skills, O*NET occupations, Kaggle/UCI datasets)
python scripts/ingest_oer.py seed --name esco_skills
python scripts/ingest_oer.py seed --name onet_occupations
python scripts/ingest_oer.py seed --name kaggle_uci_datasets

# Live arXiv query — best for Master/Doctorate-depth grounding
python scripts/ingest_oer.py arxiv --field-id data-science --query "machine learning survey"

# Any OpenStax/MIT OCW/OER Commons/etc. export you've downloaded yourself
python scripts/ingest_oer.py folder --path data/oer_raw/economics --field-id economics

python scripts/ingest_oer.py --status   # chunk count in the store
```

### What's real today vs. what needs a follow-up ingestion run

- **Live and fully working**: the arXiv connector (`sources.fetch_arxiv`) —
  a real, unauthenticated call to `export.arxiv.org`'s public API. (It
  couldn't be exercised end-to-end from this development sandbox — its
  outbound network policy blocks that host specifically — but it's a plain
  HTTPS GET against a public REST API, the same pattern already used and
  tested for the HF calls elsewhere in this app.)
- **Curated seed samples, not the full corpus**: ESCO's full skills/
  occupations taxonomy and O*NET's full occupational database are each
  multi-hundred-megabyte bulk CSV/RDF downloads; O*NET's Web Services API
  additionally requires registration credentials. Rather than fake a live
  integration against them, `seed_data/*.json` ships a small, real,
  hand-picked sample per source (6-8 entries each) so the pipeline has
  something genuine to retrieve today. To go beyond the sample: download
  ESCO's CSV export or O*NET's database files and point
  `sources.load_local_folder` at them (convert rows to the
  `{"id","title","text","url"}` JSON shape `load_local_folder` expects).
- **Bring-your-own-download**: MIT OpenCourseWare, OpenStax full textbooks,
  OpenLearn, OER Commons, and HF-hosted "OER"-tagged datasets don't have a
  small enough API to call ad hoc — download the source's own export and
  run `ingest_oer.py folder` against it.
- **Not yet wired in**: PubMed Central and SciELO (additional
  Doctorate-level primary-literature sources) — `fetch_arxiv`'s shape is a
  template for adding equivalent connectors for either.

## Faculty: named, voiced teacher personas

`backend/personas.py` replaces the single generic tutor voice with real
pedagogical identity: 5 hand-designed "core teacher" personas (selectable
in Talk Live, each with its own correction philosophy and voice) and one
dedicated professor per Academy field (~30, generated deterministically —
same field always gets the same professor). See `backend/curriculum.py`'s
`build_conversation_system_prompt` for the actual instruction set each
persona speaks under.

Portraits are FLUX-generated (see `hf_client.generate_image`, reused for
this) with a monogram fallback when unavailable; voices are steered via
Parler-TTS natural-language voice descriptions for the 8 languages it
covers (en/fr/es/pt/pl/de/it/nl), falling back to the shared MMS voice
otherwise. Both integrations were checked against the HF Hub directly
rather than assumed:

| Model | Verified status |
|---|---|
| `black-forest-labs/FLUX.1-schnell` | Gated (license must be accepted once), live on multiple Inference Providers (nscale, fal-ai, together, wavespeed) |
| `openai/whisper-large-v3` | Live on the `hf-inference` provider |
| `parler-tts/parler-tts-mini-multilingual-v1.1` | Apache-2.0, confirmed 8-language coverage matches this app's `PARLER_LANGS` exactly; no confirmed live Inference Provider at time of writing — best-effort, same as any HF call here, with a documented (not yet implemented) Space-based fallback in `hf_client.py`'s comments |
| `hexgrad/Kokoro-82M` | Considered and rejected — English-only, and its one listed provider (fal-ai) shows an error status |

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
  SUPABASE_DB_URL=... HF_TOKEN=... \
  --app language-ai-x90j9w
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
