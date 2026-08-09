# Adaptive Learning Architecture (ALA) v1

Status: **Active**. Introduced in PR #2 (`LearningState` → `AdaptationEngine` →
`Conversation` / `Curriculum` / `Exercises`).

This document is not a feature list. It's the rulebook that made three
independent PRs converge on the same shape without anyone designing that
shape up front. If you're about to add a field to `LearningState`, a new
adapter, or a new consumer, read the three rules below before writing code —
they're deliberately strict, and the strictness is the point.

## 1. What this architecture is

Three pieces, each with one job:

```
                LearningState
                (a typed snapshot of one student)
                       │
              LearningStateProvider
              (short-TTL cache in front of it)
                       │
                AdaptationEngine
        (LearningState -> one typed decision per consumer)
          ┌────────────┼────────────┐
          │             │             │
   Conversation     Curriculum     Exercises
  (prose block)   (per-unit       (per-exercise
                    weights)        priority)
```

Code: `backend/learning_engine/learning_state.py`,
`backend/learning_engine/adaptation.py`. Consumers wire in from their own
routers (`routers/conversation.py`, `routers/lessons.py`).

**What problem this solves.** Before this existed, the app had real
pedagogical signal (competencies, forgetting risk, learning style, SRS due
items, career goals) computed correctly by `learning_engine/*`, but every one
of those computations only ever fed a dashboard. Nothing fed back into what
the app actually generates or shows a learner. `LearningState` is the single
place that signal is assembled; `AdaptationEngine` is the only place it's
allowed to turn into a decision.

## 2. What counts as a real signal (the only rule that matters for `LearningState`)

Every field on `LearningState` must answer three questions before it's added.
If any answer is "not yet", the field does not go in — it goes in as
`v(n+1)` once the answer exists, or it doesn't go in at all.

1. **What is its objective source?** A named function in `learning_engine/`
   or `srs.py` that already computes it from stored data — not a number this
   PR is inventing to fill a gap. "Read off `lesson_history`" is a source.
   "Feels like it should correlate with X" is not.
2. **Which existing consumer actually uses it?** Not "a future consumer
   might". If nothing reads it yet, it doesn't belong in the canonical state
   yet either — it belongs in the PR that adds the consumer that needs it.
3. **What concrete decision does it let a consumer make?** Not "more
   context is always better." If the answer is "I'm not sure, but it feels
   relevant," it fails this test.

### Fields rejected under this rule (keep this list — it's as important as the
one that got in)

| Candidate | Why it was rejected |
|---|---|
| `fatigue` | No session-boundary tracking exists in this app (`lesson_history` rows are completion timestamps, not start/end pairs) — `motivation.py`'s own docstring calls this out explicitly. Guessing it from timestamp gaps would be a fabricated signal. |
| `confidence` (a numeric score) | A real signal already exists for this — `motivation.detect_signal()` (`frustracion` / `buen_momentum` / `estancado`). Quantizing it into a fake `0.71` doesn't add information, it adds false precision. |
| `learning_style` as visual/auditory/kinesthetic | `learning_style.py`'s own docstring: this is "a well-known, scientifically unsupported framework" with no real signal in this app linking any activity to it. What the field actually measures — conversational vs. written/structured activity ratio — is real and is what's in the state. |
| `estimated_cefr`, `predicted_next_score` | No model producing these exists. |
| Anything from an `EmbeddingProvider` | This app has three separate, explicit statements in the codebase (`rag.py`, `mentor_engine.py`, `jobs/scanner.py`) that it deliberately does not use embeddings/vector similarity, to stay dependency-light and free-tier-only. Proposing an embedding-derived field would reverse a standing decision, not extend one. |

### Current fields and their sources (as of this document)

| Field | Source |
|---|---|
| `competencies` | `learning_engine.competency.get_unified_competencies` |
| `forgetting_risk`, `dropout_risk` | `learning_engine.predictions` |
| `learning_style` | `learning_engine.learning_style.infer_learning_style` |
| `career_goal` | `learning_engine.student_profile.get_career_goal` |
| `frequent_mistakes` | `learning_engine.student_profile.frequent_mistakes` (Academy-scoped, `course_id`-keyed) |
| `due_review_items` | `srs.due_review_items` (language-scoped, `vocab_key`/`unit_id`-keyed) |
| `motivation_signal` | `learning_engine.motivation.detect_signal` |

## 3. `AdaptationEngine` invariants

These are not style preferences. Breaking any of these is the thing this
document exists to prevent.

1. **A consumer's adaptation type is shaped for that consumer, not
   universal.** `ConversationAdaptation` is a prose block. `CurriculumAdaptation`
   is per-unit weights. `ExerciseAdaptation` is per-exercise priority. There is
   no `AdaptationEngine.adapt(state) -> dict` that every consumer reinterprets.
   If a future consumer's needs don't fit any existing shape, it gets its own
   dataclass — that's cheap. Forcing it into an existing shape is not.
2. **An adapter interprets `LearningState`; it never computes a new signal.**
   `for_curriculum`/`for_exercises` do exactly one transformation each
   (`due_review_items` → a weight/priority keyed by the join field that
   exists). No adapter derives a second-order value (a "confidence
   modifier", a "difficulty score") that isn't already a `LearningState`
   field in its own right. If a transformation feels like it needs its own
   justification, that justification belongs in `LearningState` (per §2),
   not buried inside an adapter.
3. **Adaptation is presentation-only. It never touches generated content,
   and it never touches a `cache_key` or a generation prompt.** Concretely:
   `CurriculumAdaptation`/`ExerciseAdaptation` only annotate objects that
   already exist (a `UnitNode`, an `Exercise`) with a `priority`/`weight`
   field — they never reorder, regenerate, or filter the underlying list,
   and neither of their wiring points (`routers/lessons.py`'s `get_path()`
   and `get_lesson_exercises()`) is on a path that calls
   `hf_client.generate_exercises()`. `ConversationAdaptation`'s text is
   appended to an already-built system prompt; it does not participate in
   any caching, because Conversation is never cached to begin with. **If a
   future adapter's natural home is a cached, AI-generated path (Practice's
   `generate_exercises()` cache, or a future TTS/image cache), the
   contract must be extended with an explicit "applies only after content
   resolves" mechanism before that adapter is written — never as an
   afterthought.** (`generate_exercises()`'s existing, accepted
   `recent_mistakes`-in-prompt-but-not-in-cache-key tradeoff is exactly the
   failure mode this invariant exists to prevent repeating elsewhere — it
   predates this architecture and is intentionally left as-is, not a
   precedent to follow.)
4. **A join between `LearningState` and a consumer's own domain objects must
   be a real, existing key — never inferred or fuzzy-matched.**
   `CurriculumAdaptation` uses `unit_id`. `ExerciseAdaptation` uses
   `vocab_key`. Both are exact matches against fields the two sides already
   share, not a heuristic ("this grammar point is probably in this unit").
   Academy's `frequent_mistakes` (keyed by `course_id`) has no such join to
   the language track today — it is used by `ConversationAdaptation` (where
   it's Academy-native content) and correctly excluded from
   `CurriculumAdaptation`/`ExerciseAdaptation` (language-native content) for
   exactly this reason.
5. **One adapter per consumer, not one per pedagogical mode, until a second
   rule actually forces the split.** Exercises has three delivery paths
   with different constraints (Lesson: pre-built, no cache; Practice:
   AI-generated, cached; Review: personalized, never cached) but one
   `ExerciseAdaptation`, because only one adaptation rule (the `vocab_key`
   join) has evidence behind it. Split `ExerciseAdaptation` into per-mode
   types the day a second rule genuinely needs different behavior per mode
   — not preemptively.

## 4. When a new adapter is acceptable

Before writing `for_<new_consumer>`:

1. List the consumer's real, existing fields (its Pydantic model / DB
   columns) the same way `Exercise` was audited before `ExerciseAdaptation`
   was designed.
2. Find the actual join — a field name/value that already appears on both
   sides. If none exists, the work item is adding that metadata (a separate,
   smaller PR), not writing the adapter.
3. Write down, per candidate signal, which of §2's three questions it fails.
   Anything that fails one ships as a documented gap, not a guess.
4. The adapter's dataclass is shaped for exactly what that consumer needs —
   don't reuse another consumer's shape because it's convenient.
5. The consumer's own wiring point must not be on a path that caches
   AI-generated content, unless the applicability mechanism in §3.3 is
   designed first.

## 5. Explicitly not built yet, and why

These came up during design discussions and were deliberately deferred —
listed here so no one rebuilds the discussion from scratch, and so "why
isn't X done yet" has a written answer instead of relying on memory of a
conversation.

- **Per-capability provider interfaces beyond `AIProvider`/`STTProvider`**
  (`TTSProvider`, `ImageProvider`, `VideoProvider`, `EmbeddingProvider`).
  Rule that produced `AIProvider`/`STTProvider`: an interface is extracted
  when a second real implementation exists to prove its shape, never
  before. Today: chat has 3 implementations, STT has 2 — both interfaces
  are earned. Image and video generation each have exactly one provider —
  no interface yet. `EmbeddingProvider` is not "not yet" — see §2's
  rejection table, it contradicts a standing decision.
- **A capability registry** (`get_provider(Capability.STT)`). Earns its
  keep when there's real dynamic/runtime provider selection to resolve —
  by user, by cost, by region. Today both provider lists are static,
  two-to-three-item literals in `HFClient.__init__`; a registry would be a
  layer whose only job is returning that same literal.
- **`LearningConcept`** — a unifying entity so Conversation (grammar/
  vocabulary), Curriculum (`Unit.id`), SRS (`vocab_key`), and Academy
  (`concept_id`) could all reference "the same thing being learned." Real
  gap (documented in `learning_state.py`), but designing its shape with
  only two real consumers (`Curriculum`, `Exercises` — both keyed
  differently already) risks guessing at requirements a third consumer
  hasn't supplied evidence for yet.
- **Explicit `AdaptationRule` objects** (e.g. `ReviewPriorityRule`,
  `CurriculumPriorityRule`) instead of the transformation living inline
  inside each `for_<consumer>` function. Worth watching, not worth
  building: today each adapter has exactly one rule. If a consumer
  accumulates several independent, combinable rules, extracting them into
  small composable objects is the natural next step — but forcing that
  shape onto one-rule adapters now would be exactly the kind of
  unforced abstraction §3 exists to prevent.
- **Provider cost/quality metrics.** `telemetry.log_provider_resolution`
  covers `provider`/`attempt`/`fallback`/`elapsed_ms` — all real,
  measured. Cost has no per-call API on the free-tier providers this app
  uses; quality has no human-eval or user-feedback loop to grade against.
  Both stay out until a real source exists, per §2's logic applied to
  telemetry instead of `LearningState`.

## 6. References

- `backend/learning_engine/learning_state.py` — `LearningState`,
  `LearningStateProvider`.
- `backend/learning_engine/adaptation.py` — `AdaptationEngine`'s three
  adapters, and the fullest version of the reasoning summarized above (each
  adapter's module-level docstring is the source of truth if this document
  and the code ever disagree — update this document, not the other way
  around).
- `backend/ai_providers/` — `AIProvider`/`STTProvider`, extracted under the
  same "second implementation earns the interface" rule as §5.
- `backend/telemetry.py` — provider-resolution telemetry.
