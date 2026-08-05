# Auditoría de dependencias — Lingua backend (2026-08-05)

Auditoría completa de `requirements.txt`, verificada contra el código real
del backend (no contra los documentos de planificación `AI_INTEGRATION_PLAN.md`
/ `MISSING_FEATURES.md`, que describen una arquitectura aspiracional distinta
a la implementada — ver la nota agregada al inicio de cada uno).

## Metodología

1. Se extrajeron todos los `import`/`from` reales de `backend/` (no lo que
   *podría* usarse) y se compararon contra `requirements.txt`.
2. Se verificó cada versión pineada contra la última disponible en PyPI
   (`pip index versions`).
3. Se corrió `pip-audit` contra el `requirements.txt` original y contra el
   propuesto, para detectar CVEs conocidos.
4. Se instalaron las versiones propuestas en un venv limpio y se corrió la
   suite completa (`pytest`, 302 tests) para confirmar compatibilidad real,
   no solo teórica.

## Resultado: qué se mantiene, actualiza o elimina

| Paquete | Antes | Ahora | Acción | Motivo |
|---|---|---|---|---|
| `fastapi` | 0.135.0 | 0.141.1 | Actualizar | Sin CVEs pero 6 minors atrás; última estable, tests OK |
| `uvicorn[standard]` | 0.30.6 | 0.37.0 | Actualizar | Igual, backlog de parches/perf desde entonces |
| `pydantic` | 2.8.2 | 2.13.4 | Actualizar | Varias minors de mejoras/fixes en v2, sin cambios breaking para este código |
| `httpx` | 0.27.2 | 0.28.1 | Actualizar | Cliente HTTP interno de `hf_client.py`/`rag.py`/`piper_tts.py` |
| `python-multipart` | 0.0.32 | — | **Eliminar** | No usado: `grep` confirma cero `UploadFile`/`Form()` en todo el backend. El audio llega como body crudo (`request.body()` en `routers/content.py`) o base64 por WebSocket (`routers/conversation.py`), nunca como `multipart/form-data`. FastAPI solo necesita este paquete para parsear ese formato. |
| `psycopg[binary]` | 3.2.3 | 3.3.4 | Actualizar | Storage de producción (Supabase), sin cambios de API relevantes |
| `piper-tts` | 1.6.0 | 1.6.0 | Mantener | Ya es la última versión; pin justificado por licencia (ver comentario en `piper_tts.py`) |
| `gradio_client` | 2.6.0 | 2.6.0 | Mantener | Ya es la última; único cliente para el fallback verificado de Parler-TTS (voces por persona) |
| `num2words` | 0.5.14 | 0.5.14 | Mantener | Ya es la última; preprocesa dígitos para Parler-TTS |
| `pytest` | 8.3.3 | 9.1.1 | Actualizar + **mover** | `pip-audit` marcó 8.3.3 con una vulnerabilidad conocida (PYSEC-2026-1845, corregida en 9.0.3+). Movido a `requirements-dev.txt`: un framework de tests no debe viajar dentro de la imagen Docker de producción. |

Verificación post-cambio: `pip check` sin conflictos, `pip-audit` sin
vulnerabilidades conocidas en ninguno de los dos archivos, 302/302 tests
pasando.

## Reestructuración de archivos

- **`requirements.txt`** — solo dependencias de runtime, exactamente lo que
  `Dockerfile` instala en la imagen de producción.
- **`requirements-dev.txt`** (nuevo) — `-r requirements.txt` + `pytest`. Se
  usa en CI (`.github/workflows/ci.yml`) y en desarrollo local; nunca se
  instala en producción, así el contenedor de despliegue queda más chico.

No se creó `requirements-ai.txt` ni `requirements-prod.txt` porque, tras la
auditoría (ver más abajo), no hay una capa adicional de dependencias de IA
"pesadas" que justifique un tercer archivo: la única IA que corre dentro del
proceso Python es Piper (ya en `requirements.txt`); todo lo demás son
llamadas HTTP a APIs externas usando el `httpx` que ya está ahí.

## Por qué NO se agregó el stack pesado de Hugging Face / IA local

Se evaluó explícitamente cada paquete pedido. Ninguno se agrega, porque
ninguno tiene un punto de uso real en el código — y agregarlo contradice una
decisión arquitectónica ya documentada y deliberada en el propio repo
(ver el comentario en `backend/rag.py`: *"a 'real' RAG stack (LangChain, a
vector DB, a local sentence-transformers embedding model) would add hundreds
of MB of dependencies (torch) to what is currently a lightweight
`python:3.12-slim` deploy"*).

### Ecosistema Hugging Face

| Paquete | ¿Se necesita? | Justificación técnica |
|---|---|---|
| `transformers`, `diffusers`, `accelerate`, `optimum`, `peft` | No | Requieren `torch` (GBs) para *cargar y correr modelos localmente*. Este proyecto solo consume Hugging Face como **API remota** (`router.huggingface.co`, vía `httpx` puro) — nunca carga un modelo en memoria. Instalar estos paquetes sin usarlos infla la imagen Docker sin ningún beneficio funcional, y el deploy en Fly.io corre en `python:3.12-slim` con volumen de 1GB. |
| `safetensors`, `tokenizers` | No | Dependencias transitivas de `transformers`; sin `transformers` no hay razón para instalarlas sueltas. |
| `datasets` | No | Sirve para cargar/procesar datasets de HF para entrenamiento/fine-tuning. No hay pipeline de entrenamiento en este proyecto. |
| `huggingface-hub` | No directo | Ya llega transitivamente vía `gradio_client` para hablar con el Space de Parler-TTS; no hace falta pinearlo aparte porque el código nunca lo importa directamente. |
| `sentence-transformers` | No | Necesitaría `torch` para generar embeddings localmente. `rag.py` deliberadamente evita esto: usa el propio ranking de búsqueda de arXiv/Wikipedia en vez de construir un paso de embeddings/vector store. |

### Audio

| Necesidad | Solución actual | ¿Cambiar? |
|---|---|---|
| Speech-to-Text | Groq Whisper API (primario, `whisper-large-v3`, instantáneo) → fallback a HF Inference API con el mismo modelo | No. Ya es una arquitectura híbrida razonable: rápido y gratis por API, sin cargar Whisper localmente (que requeriría `torch`/`openai-whisper`/`faster-whisper` + varios GB de modelo). |
| Text-to-Speech | Piper (autoalojado, ONNX, ~53 idiomas, gratis e ilimitado) → ElevenLabs opcional (voces por persona) → Parler-TTS vía Gradio Space → HF MMS-TTS | No. Esta *ya es* la "arquitectura híbrida" que se pidió investigar: local para el caso común (gratis, sin límite), API solo para casos que Piper no cubre. Piper usa `onnxruntime` (dependencia transitiva del paquete `piper`), no `torch` — mucho más liviano. |
| Voice Cloning | No implementado | No se agrega. `personas.py` ya resuelve "identidad de voz distintiva por personaje" con *prompts descriptivos* a Parler-TTS (su mecanismo documentado), sin clonar voces reales — evita además los problemas de consentimiento/licencia de la clonación de voz. |
| Speaker Embeddings | No implementado | Sin caso de uso identificado en el producto actual (no hay verificación de hablante ni diarización). |
| Pronunciation Assessment / Forced Alignment | Parcial: el modelo de chat da feedback textual sobre la transcripción (persona "Sofía", enfocada en fonética) | Gap real, pero no se resuelve con una dependencia — requeriría un alineador fonético (p. ej. Montreal Forced Aligner, wav2vec2-based CTC alignment) y nuevos modelos/datos. Es una feature nueva, no un cambio de dependencias; se deja como ítem de roadmap, no se agrega la dependencia especulativamente. |
| Audio Segmentation / Streaming | Ya existe segmentación por oración (`piper_tts.split_into_sentences`) para streaming progresivo de audio (`hf_client.stream_speech`) | No requiere librería adicional; es texto plano + regex, suficiente para el caso de uso (paceo de TTS, no diarización). |

### LLM

| Paquete | ¿Se necesita? | Justificación técnica |
|---|---|---|
| `llama-cpp-python`, `vLLM`, `Ollama`, `mlx` | No | Todos implican **auto-alojar** un modelo de lenguaje. La arquitectura actual usa Groq (Llama-3.1-70B, gratis/rápido) → Pollinations → HF Qwen2.5-7B como fallback final, todo vía API con `httpx`. Auto-alojar un LLM en el mismo contenedor Fly de 1GB de volumen no es viable, y contradice el diseño de costo $0 documentado en `hf_client.py`. |
| `LiteLLM` | No | `hf_client.py` ya implementa su propia capa de fallback multi-proveedor (`chat()`: Groq → Pollinations → HF), con circuit breakers y presupuesto diario por proveedor (`_HFGuard`) hechos a medida para este caso. LiteLLM unificaría la *llamada*, pero no reemplaza esa lógica de guardas/cooldowns ya afinada; migrar sería reescribir código que funciona, por una abstracción que no resuelve un problema real hoy. |
| `Guidance`, `Instructor`, `Outlines` | No, por ahora | Interesante en teoría para forzar JSON válido (varios métodos de `hf_client.py` parsean JSON con regex + `try/except`), pero requieren soporte de function-calling/structured-output consistente en los tres proveedores rotados (Groq, Pollinations, HF) — no verificado. El código actual ya degrada con gracia ante JSON inválido (contenido de fallback offline en cada método), así que el riesgo de una migración no compensa la ganancia. Queda como posible mejora futura, evaluando un solo proveedor a la vez, no como dependencia agregada especulativamente. |

### Embeddings

`sentence-transformers`, `FlagEmbedding`, `faiss`, `hnswlib` — **no se
agregan**. No hay búsqueda semántica ni recuperación vectorial en el código
actual; `rag.py` usa el ranking propio de las APIs de búsqueda de arXiv y
Wikipedia. Agregar un motor de embeddings sin un caso de uso concreto (y sin
`torch`, que ya se evita deliberadamente) no cumple la regla del propio
pedido: "cada nueva dependencia debe tener un propósito claro".

### Visión

`transformers`-based OCR/VLMs y generación de imágenes local (`diffusers`)
— **no se agregan**. La generación de imágenes (flashcards de vocabulario)
ya la resuelve Pollinations (Flux) por API gratuita y sin llave, con
`GOOGLE_CSE_API_KEY` como alternativa opcional de fotos reales
(`image_search.py`). No hay OCR ni VLM en ningún flujo del producto.

### Optimización

`onnxruntime` ya está presente como dependencia transitiva de `piper-tts`
(es lo que usa Piper para inferencia local — ver `Dockerfile`, que instala
`libgomp1` específicamente para esto). `optimum`, `bitsandbytes`,
`flash-attention`, `xformers` — **no se agregan**: todas existen para
acelerar/cuantizar modelos que corren *en este proceso*, y el único modelo
que corre en este proceso es Piper (ya optimizado vía ONNX). No hay ningún
modelo de `transformers`/`diffusers` local al que optimizar.

## Compatibilidad

- `pip check` sin conflictos entre las 9 dependencias de runtime + `pytest`.
- `pip-audit` sin vulnerabilidades conocidas en ninguno de los dos archivos.
- Suite completa (302 tests) verde con las versiones nuevas, en instalación
  limpia desde los archivos finales.
- Único hallazgo no accionado: `starlette` (dependencia transitiva de
  `fastapi`) emite un `DeprecationWarning` en los tests indicando que
  `TestClient` reemplazará su dependencia de `httpx` por un paquete nuevo
  (`httpx2`) en una versión futura. `httpx2` es una librería recién liberada
  (posterior a mi corte de entrenamiento) — no se adopta todavía sin poder
  verificar su estabilidad/API con más profundidad; es solo un warning, no
  rompe nada hoy. Se deja anotado para revisar en una próxima auditoría.

## Adaptación de código

No se modificó código de `backend/` más allá de los archivos de
dependencias, CI y documentación: las actualizaciones de versión no
introdujeron cambios de API que afecten a este proyecto (confirmado por la
suite de tests), y ninguna dependencia nueva se agregó, así que no hay
código nuevo que integrar. La "arquitectura híbrida" que se pidió evaluar
para audio ya está implementada (Piper local + APIs de fallback) y es,
según esta auditoría, la decisión correcta para el perfil de este proyecto
(deploy de bajo costo, sin GPU, imagen `slim`).
