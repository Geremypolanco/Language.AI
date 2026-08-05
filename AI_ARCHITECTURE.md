# Language.AI — AI Architecture

This document replaces `AI_INTEGRATION_PLAN.md` (kept as a short pointer to
here) as the authoritative description of this app's AI architecture. It
covers: what the audit found, the new `backend/ai/` orchestration layer,
how it's wired into the rest of the app, the model choices behind it and
why, and what's deliberately out of scope for this pass.

## 1. Audit: what was actually there

`AI_INTEGRATION_PLAN.md` described an architecture — Ollama + Mistral/
Llama, Coqui TTS, a Docker Compose `ollama` service — that was **never
actually built**. It predates the real implementation and drifted into
fiction. The real, running system (`backend/hf_client.py`, `piper_tts.py`,
`personas.py`, `image_search.py`) is meaningfully more sophisticated than
that plan, and for good, documented reasons:

- **No GPU, one small container.** This app deploys as a single
  `python:3.12-slim` box on Fly.io (see `Dockerfile`/`fly.toml`). There is
  no `torch`/`transformers`/`diffusers` in `requirements.txt` — every AI
  call is an HTTP request to a hosted provider, never a locally-run model
  (Piper's tiny ONNX voices are the one exception, see §4). "Self-host
  Mistral/Llama via Ollama" was never compatible with this deployment.
- **Multi-provider chat**, not a single Ollama model: Groq (Llama-3.1-70B,
  free, near-zero latency) → Pollinations (free, keyless) → Hugging Face
  (Qwen2.5-7B-Instruct, chosen specifically for CJK/Cyrillic strength) —
  see `hf_client.chat()`.
- **A real reliability layer**: retries, an ElevenLabs circuit breaker, and
  `_HFGuard` — a shared circuit breaker + soft daily budget across every
  Hugging Face call site, because HF Inference Providers is the one
  credit-limited tier in the whole rotation.
- **Piper**, not Coqui: self-hosted, GPL-3.0, ONNX, ~53 languages, genuinely
  free and unlimited, small enough to run on a CPU-only container.
- **Named, voiced teacher personas** (`personas.py`) already existed — 5
  core teachers plus one deterministically-assigned faculty member per
  academic field — steered via ElevenLabs (opt-in) or Parler-TTS
  description prompts, not a single generic voice.
- **Pre-generated content libraries** (`academy_library/`,
  `language_library/`) already implement "build once, serve forever" for
  *text*: curricula, courses, glossaries, quizzes, exams, assignments,
  exercises, flashcards.

What was genuinely missing, and what this redesign adds: **an explicit
orchestration layer** (task → router → model, instead of every call site
importing `hf_client` directly), **embeddings/semantic search** (there was
no vector search anywhere in the app), and **audio as a first-class,
pre-generated asset** on top of that existing pre-generated text (glossaries
and flashcards had no associated audio at all before this change).

## 2. The AI Orchestrator

```
                         ┌─────────────────────┐
   Conversation ───────▶ │      LLM Router      │──▶ Groq → Pollinations → HF (Qwen2.5)
   Grading ────────────▶ │  Evaluation Router    │──▶ (reuses the LLM chain, stricter prompt)
   Talk Live / TTS ────▶ │    Speech Router      │──▶ Piper → ElevenLabs/Parler-TTS → MMS-TTS
   Flashcards / Portraits▶│    Vision Router      │──▶ real photos → Pollinations FLUX → HF FLUX
   Library search ─────▶ │  Embedding Router      │──▶ BAAI/bge-m3 (HF)
                         └──────────┬───────────┘
                                    │
                            AIOrchestrator
                        (backend/ai/orchestrator.py)
```

`backend/ai/orchestrator.py` exposes one object, `ai_orchestrator`, with
five task-specialized routers:

| Router | File | Task |
|---|---|---|
| `ai_orchestrator.llm` | `backend/ai/routers/llm.py` | chat, streaming chat, conversational replies |
| `ai_orchestrator.speech` | `backend/ai/routers/speech.py` | TTS (real-time + offline), STT |
| `ai_orchestrator.vision` | `backend/ai/routers/vision.py` | image generation, illustration (photo-first), video |
| `ai_orchestrator.embeddings` | `backend/ai/routers/embeddings.py` | text embeddings, semantic ranking |
| `ai_orchestrator.evaluation` | `backend/ai/routers/evaluation.py` | grading open answers, assignments, practice responses |

Each router's `active_chain` property reads from `backend/ai/registry.py`'s
`MODEL_REGISTRY` — the ordered, documented list of models tried for that
task (see §5). This is the concrete mechanism that keeps "which model does
X actually call" from silently drifting out of sync with a design doc.

**Design choice, stated explicitly:** these routers are a facade over
`hf_client.py`, not a rewrite of it. `hf_client.py` already contains
production-proven reliability engineering (retries, circuit breakers, the
shared HF budget guard, disk caching) that this redesign has no reason to
duplicate or risk regressing. The orchestrator's job is to be the *one
place the rest of the app reaches for AI*, organized by task instead of by
"whatever hf_client happens to expose" — not to reimplement working code.
Higher-level, disk-cached content generators that mix prompt-building +
caching + parsing for one specific content type (`generate_book_content`,
`generate_curriculum`, `generate_recommendations`, ...) intentionally stay
on `hf_client` directly rather than getting a 1:1 router wrapper — wrapping
them would add indirection with no architectural benefit, since they aren't
raw "call an LLM" primitives the way `chat()`/`embed_text()` are.

### Where it's wired in

Every one of these now imports `ai_orchestrator` instead of `hf_client`
directly:

- `routers/conversation.py` (Talk Live: transcription, streaming chat, streaming TTS)
- `routers/content.py` (`/tts`, `/image`, `/video`, `/stt`, `/tutor-reply`, `/news`, `/explain`)
- `routers/personas.py` (portraits, new `/voice` endpoint)
- `routers/library.py` (new semantic `/search` endpoint)
- `routers/academy.py` + `learning_engine/grading.py` (grading calls)
- `academy_library/generators.py`, `language_library/generators.py` (build-time content generation)
- `academy_library/build.py`, `language_library/build.py` (offline audio pre-generation, see §4)

## 3. Two voice pipelines

```
Real-Time Voice (Talk Live):
    text ──▶ Speech Router.stream() ──▶ per-sentence audio chunks ──▶ websocket ──▶ user

Offline Voice Builder (academy/language library builds):
    content ──▶ Speech Router.synthesize_asset() ──▶ audio file ──▶ settings.audio_assets_dir
              ──▶ served forever at /audio-assets/... (front with a CDN/object store in production)
```

Both pipelines call the **exact same synthesis chain** (Piper → ElevenLabs/
Parler-TTS for a persona voice → MMS-TTS), so a teacher's voice sounds
identical whether it was generated live or ahead of time. Only what happens
to the resulting bytes differs: streamed once to a websocket, or written
once to a permanent file and served by every future request.

`SpeechRouter.synthesize_asset()` (`backend/ai/routers/speech.py`) is
idempotent — a repeat call with the same inputs is a disk read, not a new
synthesis call — and safe to run on every build, including resumed ones.

## 4. Audio as a first-class asset

`backend/ai/asset_pipeline.py` is the reusable layer that gives any
already-generated text content a pre-generated, permanent audio file:

- `add_glossary_audio()` — pronounces every academy glossary term, wired
  into `academy_library/build.py`'s `glossary` step.
- `add_flashcard_audio()` — pronounces every language-library flashcard
  (using each card's `audio_text`, already the field designated for
  TTS-backed pronunciation), wired into `language_library/build.py`.

Both are **best-effort per item**: one item's synthesis failing (no Piper
voice for that language, HF budget exhausted mid-build) is logged and that
item is left with `audio_url: null` — it never aborts the rest of the
build, since audio is additive polish on top of already-valid text content,
not a required field (matching how `image_prompt`/`audio_text` already work
on `Exercise`).

`settings.audio_assets_dir` (new) is a permanent, non-evictable directory —
`cache_gc.py`'s LRU eviction only ever scans `cache_dir` — mounted at
`/audio-assets` in `main.py`. In production this directory should be
fronted by a CDN or synced to object storage, exactly the way `/public`
already would be; that's the literal "cache → CDN → user" tier from the
redesign brief. Wiring an actual CDN/object-store sync is an infrastructure
decision (which provider, cost, DNS) that belongs to whoever operates the
deployment, not something to hardcode into the app — this pass delivers the
servable, permanent asset layer underneath it.

**Exercise-level audio** (`Exercise.audio_text`, used by vocab_intro/
listen_type/speak_repeat cards) already goes through the same
`hf_client.text_to_speech` chain at *request* time via `/api/content/tts`;
pre-generating those too — so a lesson never makes a live TTS call at
all — is a natural next step using the exact same `synthesize_asset()`
primitive, intentionally left out of this pass to keep the build's added
Piper/HF workload bounded (glossaries + flashcards already cover every
piece of vocabulary a course teaches).

## 5. Teacher voices

`backend/ai/voices.py` adds `VoiceProfile` — a structured view over each
`TeacherPersona`'s existing `voice_description`, deriving explicit `rate`
("slow"/"moderate"/"fast"), `pitch`, and `style_tags` fields instead of
leaving "voz, entonación, personalidad, ritmo, pronunciación, estilo"
implicit in one prose string. The prose string is still what actually
steers Parler-TTS synthesis (that model's own documented mechanism) —
`VoiceProfile` is a parsed, queryable view over the same source of truth,
not a second, competing one. Exposed at `GET /api/personas/{id}/voice`.

## 6. Model registry — what was researched, and why

`backend/ai/registry.py` is the living research artifact behind every
routing decision, checked directly against the Hugging Face Hub while
designing this layer (download counts, task tags, live Inference Providers
support — not assumed). Highlights:

| Task | Model chosen | Why |
|---|---|---|
| Chat (primary) | Llama-3.1-70B via **Groq** | Free, near-zero latency, beats any HF-hosted 70B for this workload at no cost |
| Chat (HF fallback) | **Qwen2.5-7B-Instruct** | Verified strongest on the CJK/Cyrillic cases Groq/Pollinations are weakest on |
| Transcription | Whisper-large-v3 via **Groq**, HF as fallback | Confirmed still the strongest open multilingual ASR (5.5M–8.7M HF downloads) with live coverage |
| Speech synthesis (default) | **Piper** (local ONNX) | Free, unlimited, CPU-only — the right default, not a compromise |
| Speech synthesis (persona) | **Parler-TTS** / **ElevenLabs** | Describable or named voice identity, layered in front of Piper |
| Image generation | **FLUX** via Pollinations, HF FLUX.1-dev as documented fallback | Free, keyless, effectively unlimited |
| **Embeddings (new)** | **BAAI/bge-m3** | Confirmed: 250M+ HF downloads, MIT license, 100+ languages, live `hf-inference` provider |
| Reranking (documented, not yet wired) | **BAAI/bge-reranker-v2-m3** | Confirmed: 19M+ downloads, pairs with bge-m3; not adopted yet because today's candidate sets are already small/bounded — see §7 |
| English TTS upgrade candidate (documented, not yet wired) | **hexgrad/Kokoro-82M** | Confirmed: 103.5M downloads, best small natural-sounding English TTS; no live HF Inference Provider today, would need its own hosted-Space integration like Parler-TTS's |

Every entry states its rationale directly in code — see the module
docstring in `registry.py` for the full reasoning, including why Hugging
Face is the *primary* choice for some tasks (TTS voice steering, embeddings)
and a documented *fallback* for others (chat, images) where a free tier
that's faster or cheaper for equal-or-better quality already exists.
"Use the best model per task" means matching each task to whichever
free/cheap tier is genuinely best for it — not routing everything through
Hugging Face regardless of cost or whether a better free option exists.

## 7. Semantic search (new capability)

`GET /api/library/{user_id}/search?q=...` (`routers/library.py`) is the
first real vector-search feature in this app: `EmbeddingRouter.semantic_rank`
embeds the query and a bounded candidate set (`_MAX_SEMANTIC_CANDIDATES =
40`, pre-filtered by keyword/genre/level first) via BAAI/bge-m3, and ranks
by cosine similarity. Every embedding is disk-cached forever (an
embedding for a given text never changes), so repeated searches over
overlapping candidates only pay the network/budget cost once.

Falls back to plain substring matching when embeddings are unavailable (no
HF token, budget exhausted, a rate limit, or in tests) — search still
works, just without semantic ranking.

**Deliberately not done in this pass:** a precomputed, full-catalog (500+
title) vector index. `semantic_rank` calls one HF request per candidate
with no batch endpoint to lean on; scanning the entire catalog on every
request would be both slow and a real, unbounded Hugging Face budget cost.
A real index — computed once by a build script, loaded into memory at
startup, refreshed only when the catalog changes — is the correct next
step and is a natural extension of the exact "build once, serve forever"
pattern `academy_library`/`language_library` already use for text. Cross-
encoder reranking (BAAI/bge-reranker-v2-m3) earns its extra HF call once
that index makes larger, noisier candidate sets the norm.

## 8. Optimization already in place

Most of the "lazy loading / caching / streaming / background workers" list
from the redesign brief was already implemented, and this pass reuses it
rather than building a parallel system:

- **Disk caching, forever, per content type** — every generation (chat,
  images, TTS, embeddings) is cached by a content hash; see `hf_client._cache_path`.
- **LRU eviction** for the regenerable cache (`cache_gc.py`) vs. **permanent
  storage** for published content (`academy_library_dir`, `language_library_dir`,
  and now `audio_assets_dir`) — a deliberate, existing split this redesign
  extends rather than replaces.
- **Streaming** — chat tokens and TTS sentences both stream to the client
  incrementally (`stream_chat`, `stream_speech`/`SpeechRouter.stream`).
- **Background workers** — `cache_gc.run_periodic_gc` (periodic disk GC),
  `_refresh_memory` (fire-and-forget conversation-memory updates).
- **Budget/circuit-breaker guarding** (`_HFGuard`, ElevenLabs breaker) —
  the closest existing analog to "rate limiting a shared resource," reused
  as-is by every new HF call this redesign adds (embeddings included).
- **Resumable, idempotent build pipelines** — a build that's interrupted
  and re-run skips whatever's already persisted (`academy_library/build.py`,
  `language_library/build.py`, and now their audio steps).

**Deliberately not attempted:** GPU sharing, model pooling, and batch
inference for self-hosted models. This deployment has no GPU and no
`torch`/`transformers`/`diffusers` dependency (see §1) — every model this
app calls runs on someone else's infrastructure (Groq, Pollinations,
Hugging Face's Inference Providers, ElevenLabs) via a plain HTTPS request,
except Piper's tiny CPU-only ONNX voices. "GPU sharing" and "batch
inference" describe *serving your own model weights*; adopting them would
mean provisioning GPU infrastructure this app doesn't have and taking on
real hosting cost — an infrastructure decision for whoever operates this
deployment to make deliberately, not something to bolt on silently inside
an architecture refactor.

## 9. Explicitly out of scope, and why

Several categories from the original research brief (OCR, NER, toxicity
detection, emotion detection, dedicated reranking, voice cloning, a
full-catalog vector index, document parsing, knowledge retrieval beyond
arXiv/Wikipedia) are **not implemented** in this pass. Each would be real,
separate work — a new endpoint, a new content type, or (for OCR/NER/
toxicity/emotion) a capability nothing in this app's current feature set
actually calls yet. Bundling all of them into one change alongside a
foundational orchestrator rewrite would risk shipping several
half-integrated features instead of one coherent, tested one. They're
listed here, not silently dropped, as the natural next slice of work once
a product need (a specific screen, a specific student-facing feature)
actually calls for one of them.
