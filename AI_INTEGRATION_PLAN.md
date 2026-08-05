# Language.AI - AI Integration Architecture (superseded)

This document described a planned architecture (Ollama + Mistral/Llama,
Coqui TTS, a Docker Compose `ollama` service) that was **never actually
built**. The real, running system diverged from it early on — see
[`AI_ARCHITECTURE.md`](./AI_ARCHITECTURE.md) for what's actually
implemented today: a multi-provider chat chain (Groq → Pollinations →
Hugging Face), self-hosted Piper TTS, named/voiced teacher personas, a
central `AIOrchestrator` with task-specialized routers (LLM, Speech,
Vision, Embeddings, Evaluation), a Hugging Face model registry with
research-backed rationale per task, two text-to-speech pipelines
(real-time + offline pre-generation), and the reasoning behind every one of
those choices.

This file is kept only so old links/history don't 404; treat
`AI_ARCHITECTURE.md` as the source of truth going forward.
