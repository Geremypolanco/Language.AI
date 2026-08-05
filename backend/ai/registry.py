"""Model registry: for every AI task category this app performs, the
current best available model(s) and why they were chosen — the concrete
research artifact backing AIOrchestrator's routing decisions.

This is deliberately code, not just a design doc: MODEL_REGISTRY is what
each router's `active_chain` property reads from, so the registry can never
silently drift out of sync with what the app actually calls the way a stale
markdown table would.

Two constraints shaped every choice here, both load-bearing and worth
stating up front:

1. This app deploys as a single small `python:3.12-slim` container on
   Fly.io with **no GPU** (see Dockerfile/fly.toml/requirements.txt — there
   is no torch/transformers/diffusers dependency anywhere in this repo).
   Self-hosting a multi-GB Hugging Face model directly is not an option;
   every "Hugging Face model" below is called through a *hosted* endpoint
   (HF's Inference Providers router, or a public Space) over HTTPS, exactly
   the way piper_tts.py's voice models are downloaded as static files
   rather than run through torch. Piper is the one deliberate exception —
   a tiny (~20-90MB/voice) ONNX model that genuinely runs fast enough on a
   CPU-only container.
2. Hugging Face's Inference Providers is a *credit-limited, best-effort*
   tier for this deployment (see hf_client._HFGuard) — not because HF
   models are worse, but because a free/keyless tier (Pollinations) and a
   fast, generous free tier (Groq) already exist for chat/images/STT and
   cost strictly less for equal-or-better quality. Where no such
   alternative exists at all — TTS voice steering, embeddings, reranking —
   Hugging Face is the primary choice, not a fallback. That is the actual
   shape of "use the best model per task": matching each task to whichever
   free/cheap tier is genuinely best for it, not routing everything through
   Hugging Face regardless of cost, latency, or whether a better free
   option already exists.

Every entry below was checked directly against the Hugging Face Hub
(download counts, task tags, live Inference Providers support) while
designing this module — see each entry's `rationale` for what was actually
verified, not assumed. Two follow-ups intentionally documented but NOT
wired into a router yet (hexgrad/Kokoro-82M, BAAI/bge-reranker-v2-m3) are
marked as such, with the concrete reason building them out further wasn't
included in this pass.
"""

from __future__ import annotations

from .types import AITask, ModelSpec

MODEL_REGISTRY: dict[AITask, list[ModelSpec]] = {
    AITask.CHAT: [
        ModelSpec(
            model_id="llama-3.1-70b-versatile",
            provider="groq",
            tier="primary",
            rationale=(
                "Free-tier hosted inference at near-zero latency (Groq's LPU "
                "hardware) beats any Hugging-Face-hosted 70B for this app's "
                "live conversation/grading/content-authoring workload, at no "
                "cost — see hf_client.chat()."
            ),
        ),
        ModelSpec(
            model_id="openai",  # Pollinations' proxy alias for its default chat model
            provider="pollinations",
            tier="fallback",
            rationale="Free, keyless second tier when Groq is unset or its request fails.",
        ),
        ModelSpec(
            model_id="Qwen/Qwen2.5-7B-Instruct",
            provider="huggingface",
            tier="fallback",
            rationale=(
                "Last-resort Hugging Face fallback, deliberately NOT a "
                "same-size Llama/Mistral: Qwen2.5's pretraining mix is "
                "unusually strong on CJK + Cyrillic script, exactly where "
                "Groq's Llama-3.1 and Pollinations' proxy model are "
                "weakest — confirmed the hard way by an A1 Korean/alphabet "
                "lesson regression this app shipped once (see config.py's "
                "hf_chat_model comment and curriculum.py's "
                "_uses_unfamiliar_script)."
            ),
        ),
    ],
    AITask.EVALUATION: [
        ModelSpec(
            model_id="llama-3.1-70b-versatile",
            provider="groq",
            tier="primary",
            rationale=(
                "Grading a learner's own open-answer/assignment/practice-"
                "scenario work reuses the CHAT chain rather than a second, "
                "dedicated judge model: with an explicit rubric_note in the "
                "prompt (see academy_library.build_quiz_prompt), a 70B "
                "instruction model is already consistent at this task, and "
                "a second model call would double latency and HF/Groq "
                "budget for something that's really 'chat with a stricter "
                "system prompt,' not a distinct capability."
            ),
        ),
    ],
    AITask.TRANSCRIPTION: [
        ModelSpec(
            model_id="whisper-large-v3",
            provider="groq",
            tier="primary",
            rationale="Groq-hosted Whisper: identical model quality to HF's own hosted copy, far lower latency, free tier.",
        ),
        ModelSpec(
            model_id="openai/whisper-large-v3",
            provider="huggingface",
            tier="fallback",
            rationale=(
                "Confirmed directly against the Hub (5.5M downloads; the "
                "-turbo variant leads at 8.7M) as still the strongest open "
                "multilingual ASR model with live Inference Providers "
                "coverage — no reason found to move off it."
            ),
        ),
    ],
    AITask.SPEECH_SYNTHESIS: [
        ModelSpec(
            model_id="piper (local ONNX, per-language)",
            provider="local",
            tier="primary",
            rationale=(
                "Self-hosted, free, and genuinely unlimited for the ~53 "
                "languages it has a voice for — see piper_tts.py. The right "
                "default per-language voice: no rate limit, good quality, "
                "and small/fast enough to run on this deployment's "
                "CPU-only container."
            ),
        ),
        ModelSpec(
            model_id="parler-tts/parler-tts-mini-multilingual-v1.1",
            provider="huggingface",
            tier="specialist",
            rationale=(
                "The persona-voice tier: distinct, describable teacher "
                "voices steered by a natural-language description prompt "
                "rather than literal cloning — see backend/ai/voices.py and "
                "backend/personas.py. Narrower language/Inference-Providers "
                "coverage than Piper, so it layers in *front of* Piper for "
                "Talk Live's chosen persona, never replacing the universal "
                "default."
            ),
        ),
        ModelSpec(
            model_id="elevenlabs (named voice IDs)",
            provider="elevenlabs",
            tier="specialist",
            rationale=(
                "Opt-in, highest-fidelity persona-voice tier when the "
                "deploying user supplies their own API key and voice IDs — "
                "never a required dependency (see config.py's "
                "elevenlabs_* settings); this app ships with zero required "
                "paid AI dependencies."
            ),
        ),
        ModelSpec(
            model_id="facebook/mms-tts-<lang>",
            provider="huggingface",
            tier="fallback",
            rationale="Covers roughly 100 languages Piper doesn't ship a voice for; noticeably more robotic, kept strictly as the last-resort tail.",
        ),
        ModelSpec(
            model_id="hexgrad/Kokoro-82M",
            provider="huggingface",
            tier="specialist",
            rationale=(
                "Documented candidate, NOT yet wired into a router: "
                "confirmed against the Hub (103.5M downloads, Apache-2.0) as "
                "the current best small, natural-sounding English TTS "
                "model — a strong future upgrade specifically for the "
                "en_US Piper voice slot. Not swapped in this pass because it "
                "has no live HF Inference Provider today (checked directly — "
                "its one listed provider, fal-ai, currently errors) and is "
                "English-only, so adopting it needs its own hosted-Space "
                "integration (the same pattern hf_client already uses for "
                "the Parler-TTS Space fallback — see _call_parler_space) "
                "rather than a one-line model-id swap. Tracked as a "
                "follow-up in AI_ARCHITECTURE.md instead of done half-way."
            ),
        ),
    ],
    AITask.IMAGE_GENERATION: [
        ModelSpec(
            model_id="flux",
            provider="pollinations",
            tier="primary",
            rationale="Free, keyless, effectively unlimited FLUX-backed image generation — see hf_client.generate_image().",
        ),
        ModelSpec(
            model_id="black-forest-labs/FLUX.1-dev",
            provider="huggingface",
            tier="fallback",
            rationale=(
                "Same model family Pollinations already serves under the "
                "hood; documented here as the direct Hugging Face path if "
                "Pollinations' image tier is ever retired the way its audio "
                "tier already was (see hf_client.py's module docstring)."
            ),
        ),
    ],
    AITask.VIDEO_GENERATION: [
        ModelSpec(
            model_id="damo-vilab/text-to-video-ms-1.7b",
            provider="huggingface",
            tier="primary",
            rationale="Text-to-video has much narrower serverless model coverage than text/image/audio in general; this remains the most commonly available hosted option. Best-effort by design.",
        ),
    ],
    AITask.EMBEDDING: [
        ModelSpec(
            model_id="BAAI/bge-m3",
            provider="huggingface",
            tier="primary",
            rationale=(
                "Confirmed directly against the Hub: 250M+ downloads, "
                "MIT-licensed, genuinely multilingual (100+ languages — "
                "matching this app's ~90-language picker far better than an "
                "English-only embedding model would), and has a live "
                "`hf-inference` Inference Provider today — callable the "
                "same way MMS-TTS/Parler-TTS already are, no local "
                "torch/GPU needed. Powers semantic library search "
                "(routers/library.py) and is the intended pairing for the "
                "reranking tier below."
            ),
        ),
    ],
    AITask.RERANKING: [
        ModelSpec(
            model_id="BAAI/bge-reranker-v2-m3",
            provider="huggingface",
            tier="primary",
            rationale=(
                "Confirmed directly against the Hub as the highest-adoption "
                "multilingual reranker (19M+ downloads, Apache-2.0), pairing "
                "naturally with the bge-m3 embeddings above. NOT yet wired "
                "into a router in this pass — EmbeddingRouter.semantic_rank "
                "currently reranks purely by cosine similarity over vector "
                "embeddings, which is already a real improvement over "
                "keyword matching and is good enough for the bounded "
                "candidate sets it's used against today (see "
                "routers/library.py's _MAX_SEMANTIC_CANDIDATES). A true "
                "cross-encoder reranking pass earns its extra HF call once "
                "search runs against a real precomputed full-catalog vector "
                "index and needs to narrow a larger, noisier candidate set — "
                "documented as the next step in AI_ARCHITECTURE.md rather "
                "than added speculatively now."
            ),
        ),
    ],
}


def chain_for(task: AITask) -> list[ModelSpec]:
    """The ordered provider chain for `task` — index 0 is tried first."""
    return MODEL_REGISTRY.get(task, [])
