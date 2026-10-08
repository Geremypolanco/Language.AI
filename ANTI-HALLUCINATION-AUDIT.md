# Anti-Hallucination Audit — Language.AI

**Date:** 2026-10-07 · **Ordered by:** Geremy Polanco (repo owner)
**Standard applied:** U2 (validate every LLM output against a schema; retry ≤3 with backoff; dead-letter on persistent failure — never invent data), U3 (LLM at the edges, deterministic math at the core), U5 (facts shown to the user carry provenance; without provenance they are not shown).

**Architecture note:** this repo funnels ALL LLM traffic through one gateway — `backend/hf_client.py::HFClient` (Groq Llama-3.1-70B primary → Pollinations → Hugging Face Qwen2.5 last resort). There are no other LLM providers in the codebase (no openai/anthropic/litellm/ollama imports anywhere). That single choke point is what the hardening wraps.

## Call-site inventory

| # | File | Produces | Risk | Why |
|---|------|----------|------|-----|
| 1 | `backend/hf_client.py::generate_exercises` | Exercise JSON → `Exercise` objects served as lesson content | **HIGH** | Model output decides `correct_answer`; a valid-JSON-but-wrong answer silently becomes a "correct" answer. Had NO retry on bad JSON (immediate fallback). |
| 2 | `backend/hf_client.py::generate_review_exercises` | Graded review exercises tied to the learner's vocab keys | **HIGH** | Wrong `correct_answer` corrupts spaced-repetition grading. Same no-retry gap as #1. |
| 3 | `backend/hf_client.py::grade_open_answer` | `{passed, feedback}` → feeds the competency score | **HIGH** | A hallucinated `passed: true` corrupts `competency.py` scores. Also: old code did `bool(data.get("passed"))` — the string `"false"` is truthy in Python, so a model writing `"passed": "false"` was graded as PASSED. Fails closed on exception already (good). |
| 4 | `backend/hf_client.py::grade_assignment_submission` | `{grade, feedback}` persisted to DB + shown in portfolio | **MED** | Qualitative; persisted as evidence of work. Malformed JSON was silently tolerated (`data.get("grade", "")`). |
| 5 | `backend/hf_client.py::generate_recommendations` | "Real" books/songs/podcasts/shows shown to the learner | **HIGH** | Prompt asks for real items and says "do not invent titles" — but nothing verifies it. A fabricated title presented as a real book is a textbook hallucination. (No offline verifier exists; contract + dead-letter is the enforceable part.) |
| 6 | `backend/routers/content.py::get_daily_news` | "News summaries for today" presented as news | **HIGH** | Docstring claims RAG; the prompt performs NO retrieval — pure generation presented as news. Highest fabrication surface in the app. (Endpoint is currently not called by the frontend.) |
| 7 | `backend/language_library/generators.py::generate_unit_exercises` | Build-time unit exercise batches | **MED** | Already retries 3× with `validators.validate_exercise_list` and raises `GenerationError` (loud, build fails visibly). Gap: failure left no triage record. |
| 8 | `backend/academy_library/generators.py::_generate_validated` | Build-time curriculum/course/quiz/exam/glossary/scenario content | **MED** | Same 3× retry + `GenerationError` pattern as #7 (loud). Gap: no triage record; RAG-grounded curriculum carried NO provenance into the persisted asset. |
| 9 | `backend/hf_client.py::conversation_reply` | Free-text tutor reply (Talk Live + `/tutor-reply`) | **LOW** | Conversational copy only; no facts acted on. Had a fallback string already. |
| 10 | `backend/hf_client.py::grade_practice_response` | Qualitative scenario feedback text (persisted to portfolio) | **LOW** | Copy only; already had a fallback. |
| 11 | `backend/routers/conversation.py::_refresh_memory` | Background long-term memory summary written to DB | **LOW** | Copy only, but a garbage/empty write would poison future prompts. Now gated on non-empty. |
| 12 | `backend/routers/content.py::explain_text` ("Magic Lens") | Free-text word/phrase explanation | **LOW** | Copy only. Previously a chat failure raised → HTTP 500. |
| — | `generate_image` / `generate_video` / `text_to_speech` / `speech_to_text` | Rendered media bytes, transcripts | **N/A** | Specialist renderers, not factual claims. STT returns `""` on failure, never a fabricated transcript. Out of scope by design. |
| — | `backend/personas.py` | Teacher persona definitions | **N/A** | Deterministic dataclasses; no LLM involved. |
| — | `learning_engine/grading.py` (MCQ/true-false), `learning_style.py`, `srs.py` | Scores, style inference, scheduling | **N/A** | Already U3: pure deterministic functions over stored data. Untouched. |

## What was hardened (2026-10-07)

New package `backend/llm_contracts/` (Python port of the `llm-contracts` + U5 standard):

- **`schemas.py`** — pydantic contracts for every structured LLM output: `ExerciseJSON` (+ `EXERCISE_LIST`), `ReviewExerciseJSON` (+ `REVIEW_EXERCISE_LIST`), `AssignmentGrade`, `OpenAnswerGrade`, `RecommendationItem` (+ `RECOMMENDATION_LIST`), `NewsArticle` (+ `NEWS_LIST`), `NonEmptyText` (free-text gate). Bounded strings, enums for `type`/`kind`, `passed` as real `bool` (kills the `"false"`-is-truthy bug).
- **`validate.py`** — `validate_or_retry(fn, schema, …)`: runs the fetch, validates, retries with exponential backoff (max 3 attempts), and on exhaustion pushes a `DeadLetterEntry` and returns `(False, None)`. Never invents or pads data.
- **`dead_letter.py`** — `DeadLetterQueue` with JSONL persistence to `data/dead_letters/dead_letters.jsonl` (gitignored; override via `LINGUA_DEAD_LETTER_DIR`), in-memory list, newest-first triage listing, module singleton `dead_letters`.
- **`citations.py`** — U5: `fuente:id` citation format (`CITATION_RE`), `require_citations()` fail-fast gate, and `grounding_citations()` — a pure function deriving `arxiv:<slug>` / `wikipedia:<slug>` citations from the RAG grounding text (provenance is *computed*, never extracted from the LLM).

Wrapping (behavior-preserving; every failure path keeps its pre-existing honest fallback):

- `hf_client.generate_exercises` / `generate_review_exercises` — fetch+parse now goes through `validate_or_retry`; validated items are converted to `Exercise` by pure deterministic converters (`_exercise_from_contract`, `_review_exercise_from_contract` — U3). Persistent failure → dead-letter + the existing offline fallback content (which labels itself as offline).
- `hf_client.grade_open_answer` — contract-validated; persistent failure → dead-letter + fail-closed `(False, honest message)` (unchanged semantics).
- `hf_client.grade_assignment_submission` — contract-validated; persistent failure → dead-letter + existing empty-grade fallback.
- `hf_client.generate_recommendations` — contract-validated list; persistent failure → dead-letter + existing fallback item.
- `hf_client.conversation_reply` / `grade_practice_response` — non-empty-text gate; failure → existing fallback strings (unchanged).
- `routers/content.py::get_daily_news` — article list contract-validated; failure → existing "News Unavailable" fallback.
- `routers/content.py::explain_text` — non-empty gate; failure → honest message instead of HTTP 500.
- `routers/conversation.py::_refresh_memory` — memory write gated on non-empty validated text.
- Build-time: `language_library/generators.py::generate_unit_exercises` and `academy_library/generators.py::_generate_validated` now push a dead-letter entry (with unit/content-type context) before raising `GenerationError` — failures are triage-visible, still loud.
- U5: `academy_library/generators.py::generate_curriculum` derives `sources` deterministically from the arXiv/Wikipedia grounding text and persists them on the curriculum asset; if grounding text existed but zero citations could be derived, it dead-letters and raises instead of persisting unattributed content.

## Residual risks (not eliminable without changing the product)

1. **#5 recommendations / #6 news can still name non-existent items.** There is no offline oracle for "does this book exist". Contracts bound the shape, not the truth. *Plan:* add an optional verification pass (Open Library / Google Books API lookup for books, Spotify/Web Search for songs) behind a flag; until then the prompt's "do not invent" instruction + dead-letter on malformed output is the enforcement.
2. **#6 news has no retrieval behind it** despite the "RAG" docstring. *Plan:* either wire a real news feed (RSS) as grounding with `news:<id>` citations, or relabel the endpoint as AI-generated reading practice. Frontend does not consume it today, so either is safe.
3. **Open-answer grading (#3) is inherently judgment-based.** The contract guarantees shape; the judgment stays the LLM's. Mitigation in place: fail-closed, and scores are one input among deterministic ones in `competency.py`.
4. **No live LLM calls were made during this work** (test env disables AI); the retry/dead-letter paths are exercised with fakes in `tests/test_llm_contracts.py`.

## Triage

Dead letters persist to `data/dead_letters/dead_letters.jsonl` (one JSON object per line; gitignored, never committed). Inspect with:
`python -c "from backend.llm_contracts.dead_letter import dead_letters; [print(e) for e in dead_letters.list()]"` (repo root).
