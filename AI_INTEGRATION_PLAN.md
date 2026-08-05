# Language.AI - AI Integration Architecture

> **Nota (auditoría de dependencias, 2026-08):** este documento es un plan de
> arquitectura temprano y **no refleja la implementación actual**. El backend
> real (`backend/hf_client.py`, `backend/piper_tts.py`, `backend/rag.py`) usa
> un stack basado en APIs (Groq, Pollinations.ai, Hugging Face Inference API,
> ElevenLabs opcional) más Piper TTS autoalojado — deliberadamente sin Ollama,
> sin Whisper/Stable Diffusion/spaCy locales ni `torch`, para mantener la
> imagen Docker ligera (`python:3.12-slim`) y el costo en $0. Ver
> `requirements.txt` para las dependencias realmente instaladas.

## Overview
Integrar múltiples AIs open source en toda la aplicación para que cada rincón esté vivo con inteligencia artificial.

---

## 1. CORE AI SERVICES

### 1.1 LLM Backend (Ollama + Mistral/Llama)
**Purpose:** Tutor conversacional, generación de contenido, feedback
**Models:**
- Mistral 7B (rápido, bajo costo)
- Llama 2 13B (mejor calidad)
- Neural Chat (optimizado para conversación)

**Integration:**
```python
# backend/ai_services/llm.py
from ollama import Client

client = Client(host='http://localhost:11434')

async def generate_lesson_feedback(user_answer, correct_answer):
    response = client.generate(
        model='mistral',
        prompt=f"User said: {user_answer}\nCorrect: {correct_answer}\nProvide feedback:",
        stream=False
    )
    return response['response']
```

**Endpoints:**
- `POST /api/ai/feedback` - Feedback en tiempo real
- `POST /api/ai/explain` - Explicar conceptos
- `POST /api/ai/generate-lesson` - Generar lecciones personalizadas

---

### 1.2 Speech-to-Text (Whisper)
**Purpose:** Grabar y transcribir pronunciación del usuario
**Model:** OpenAI Whisper (open source)

**Integration:**
```python
# backend/ai_services/speech.py
import whisper

model = whisper.load_model("base")

async def transcribe_audio(audio_file):
    result = model.transcribe(audio_file)
    return {
        "text": result["text"],
        "language": result["language"],
        "confidence": result.get("confidence", 0.9)
    }
```

**Endpoints:**
- `POST /api/ai/transcribe` - Transcribir audio
- `POST /api/ai/pronunciation-check` - Evaluar pronunciación

---

### 1.3 Text-to-Speech (TTS)
**Purpose:** Pronunciación nativa, lecciones de audio
**Options:**
- Coqui TTS (open source, buena calidad)
- gTTS (Google, simple)
- Piper TTS (ligero, rápido)

**Integration:**
```python
# backend/ai_services/tts.py
from TTS.api import TTS

tts = TTS(model_name="tts_models/en/ljspeech/glow-tts", gpu=True)

async def generate_speech(text, language="en"):
    audio_path = f"/tmp/speech_{uuid.uuid4()}.wav"
    tts.tts_to_file(text=text, file_path=audio_path)
    return audio_path
```

**Endpoints:**
- `GET /api/ai/speak?text=...` - Generar audio
- `GET /api/ai/lesson-audio/{lesson_id}` - Audio de lecciones

---

### 1.4 Embedding & Semantic Search (Sentence Transformers)
**Purpose:** Buscar lecciones similares, recomendaciones
**Model:** all-MiniLM-L6-v2 (rápido, 384 dims)

**Integration:**
```python
# backend/ai_services/embeddings.py
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

async def find_similar_lessons(query, top_k=5):
    query_embedding = model.encode(query)
    # Buscar en base de datos con FAISS/Pinecone
    results = vector_db.search(query_embedding, top_k)
    return results
```

**Endpoints:**
- `GET /api/ai/recommendations?user_id=...` - Lecciones recomendadas
- `POST /api/ai/search` - Búsqueda semántica

---

### 1.5 Image Generation (Stable Diffusion)
**Purpose:** Generar ilustraciones para lecciones
**Model:** Stable Diffusion XL (via Hugging Face API o local)

**Integration:**
```python
# backend/ai_services/image_gen.py
from diffusers import StableDiffusionPipeline

pipe = StableDiffusionPipeline.from_pretrained("runwayml/stable-diffusion-v1-5")

async def generate_lesson_image(prompt):
    image = pipe(prompt).images[0]
    image_path = f"/tmp/lesson_{uuid.uuid4()}.png"
    image.save(image_path)
    return image_path
```

**Endpoints:**
- `POST /api/ai/generate-image` - Generar imagen
- `GET /api/lessons/{id}/illustration` - Ilustración de lección

---

### 1.6 Named Entity Recognition (spaCy)
**Purpose:** Extraer vocabulario, identificar conceptos
**Model:** en_core_web_sm (rápido)

**Integration:**
```python
# backend/ai_services/nlp.py
import spacy

nlp = spacy.load("en_core_web_sm")

async def extract_vocabulary(text):
    doc = nlp(text)
    entities = [(ent.text, ent.label_) for ent in doc.ents]
    return entities
```

**Endpoints:**
- `POST /api/ai/extract-vocab` - Extraer vocabulario
- `POST /api/ai/analyze-text` - Análisis lingüístico

---

## 2. FRONTEND AI INTEGRATIONS

### 2.1 Real-time Feedback Component
```tsx
// client/src/components/AIFeedback.tsx
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function AIFeedback({ userAnswer, correctAnswer }) {
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const getFeedback = async () => {
      const response = await api.post("/api/ai/feedback", {
        user_answer: userAnswer,
        correct_answer: correctAnswer,
      });
      setFeedback(response.data.feedback);
      setLoading(false);
    };
    getFeedback();
  }, [userAnswer, correctAnswer]);

  return (
    <div className="p-4 bg-blue-50 rounded-lg">
      {loading ? <p>AI is thinking...</p> : <p>{feedback}</p>}
    </div>
  );
}
```

### 2.2 AI Tutor Chat Widget
```tsx
// client/src/components/AITutor.tsx
- Real-time WebSocket connection
- Streaming responses
- Typing indicator
- Context-aware suggestions
```

### 2.3 Pronunciation Analyzer
```tsx
// client/src/components/PronunciationAnalyzer.tsx
- Record audio
- Send to Whisper
- Compare with native speaker
- Visual feedback (waveform, confidence)
```

### 2.4 Smart Recommendations
```tsx
// client/src/components/AIRecommendations.tsx
- Personalized lesson suggestions
- Based on user level & interests
- Semantic search
- "You might like..." cards
```

---

## 3. PAGE-BY-PAGE AI FEATURES

### 3.1 LOGIN PAGE
- **AI Feature:** Smart onboarding assistant
- **Implementation:** Chatbot que guía el setup
- **Endpoint:** `POST /api/ai/onboarding-chat`

### 3.2 PATH (Lecciones)
- **AI Features:**
  - Generación dinámica de lecciones
  - Feedback en tiempo real
  - Explicaciones personalizadas
- **Endpoints:**
  - `POST /api/ai/generate-lesson`
  - `POST /api/ai/feedback`
  - `POST /api/ai/explain`

### 3.3 PRACTICE
- **AI Features:**
  - Evaluación automática
  - Sugerencias de mejora
  - Dificultad adaptativa
- **Endpoints:**
  - `POST /api/ai/evaluate-answer`
  - `POST /api/ai/suggest-improvement`
  - `POST /api/ai/adjust-difficulty`

### 3.4 UNIVERSITY
- **AI Features:**
  - Recomendación de carreras
  - Generación de currículum
  - Análisis de progreso académico
- **Endpoints:**
  - `POST /api/ai/recommend-career`
  - `POST /api/ai/generate-curriculum`

### 3.5 PROGRESS
- **AI Features:**
  - Análisis predictivo
  - Insights personalizados
  - Predicción de próximo nivel
- **Endpoints:**
  - `GET /api/ai/progress-insights`
  - `GET /api/ai/predict-next-level`

### 3.6 TALK (Conversación)
- **AI Features:**
  - Conversación fluida con Mistral
  - Transcripción con Whisper
  - Pronunciación con TTS
  - Feedback de pronunciación
- **Endpoints:**
  - `WS /ws/ai-conversation`
  - `POST /api/ai/transcribe`
  - `GET /api/ai/speak`

### 3.7 LIBRARY
- **AI Features:**
  - Generación de historias
  - Recomendaciones personalizadas
  - Análisis de dificultad
  - Vocabulario extraído automáticamente
- **Endpoints:**
  - `POST /api/ai/generate-story`
  - `GET /api/ai/story-recommendations`
  - `POST /api/ai/extract-story-vocab`

---

## 4. DEPLOYMENT ARCHITECTURE

### 4.1 Docker Compose Setup
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8100:8100"
    environment:
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - ollama
      - redis

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"

volumes:
  ollama_data:
```

### 4.2 Fly.io Deployment
- Backend: Python FastAPI + Ollama
- Frontend: React + Vite
- Redis: Cache & session management
- Volumes: Ollama models, audio files

---

## 5. IMPLEMENTATION ROADMAP

### Phase 1 (Week 1): Core LLM
- [ ] Setup Ollama + Mistral
- [ ] Create `/api/ai/feedback` endpoint
- [ ] Integrate in Path page

### Phase 2 (Week 2): Speech
- [ ] Setup Whisper
- [ ] Create `/api/ai/transcribe` endpoint
- [ ] Integrate in Talk page

### Phase 3 (Week 3): TTS & Images
- [ ] Setup Coqui TTS
- [ ] Setup Stable Diffusion
- [ ] Generate lesson illustrations

### Phase 4 (Week 4): Advanced Features
- [ ] Embeddings & recommendations
- [ ] NER for vocabulary extraction
- [ ] Adaptive difficulty

---

## 6. PERFORMANCE OPTIMIZATION

### Caching
```python
@cache.cached(timeout=3600)
async def get_recommendations(user_id):
    # Expensive operation
    pass
```

### Async Processing
```python
# Use Celery for long-running tasks
@app.task
def generate_story(prompt):
    return ai_service.generate_story(prompt)
```

### Model Quantization
- Use ONNX for inference speedup
- Quantize models to int8
- Use smaller models (7B instead of 13B)

---

## 7. COST ESTIMATION

| Service | Model | Cost/Month | Notes |
|---------|-------|-----------|-------|
| LLM | Mistral 7B | $0 | Self-hosted |
| Speech-to-Text | Whisper | $0 | Open source |
| TTS | Coqui | $0 | Open source |
| Image Gen | SD XL | $0 | Self-hosted |
| Embeddings | MiniLM | $0 | Self-hosted |
| Inference | Hugging Face | $10-50 | Optional CDN |
| **TOTAL** | | **$0-50** | All open source |

---

## 8. SECURITY & PRIVACY

- All models run locally (no data sent to external APIs)
- User data encrypted at rest
- Audio files deleted after processing
- No tracking or telemetry

---

## 9. MONITORING & LOGGING

```python
# backend/monitoring.py
import logging
from prometheus_client import Counter, Histogram

ai_requests = Counter('ai_requests_total', 'Total AI requests')
ai_latency = Histogram('ai_latency_seconds', 'AI latency')

@ai_latency.time()
async def call_ai_service(service_name):
    ai_requests.inc()
    # ...
```

---

## 10. NEXT STEPS

1. **Setup Ollama locally** → Pull Mistral model
2. **Create AI service layer** → Wrap all AI calls
3. **Implement caching** → Redis for responses
4. **Add monitoring** → Prometheus + Grafana
5. **Deploy to Fly.io** → Docker Compose
6. **Test end-to-end** → All pages with AI features
7. **Optimize performance** → Model quantization, batching
8. **Scale inference** → Load balancing, multiple replicas
