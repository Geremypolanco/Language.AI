# Language.AI

Aplicación web de IA con una arquitectura backend/frontend orientada a seguridad y cumplimiento normativo (GDPR/CCPA), construida con **Node.js + Express** y **React (Vite)**.

## Estructura

```
server/   API Express: seguridad, rate limiting, guardrails de IA, consentimiento de cookies
client/   SPA React: banner de cookies, chat, alertas de límite de tasa, disclaimer, feedback
```

## Módulos implementados

1. **Cookies (GDPR/CCPA)** — `client/src/components/CookieConsentBanner.jsx` + `client/src/context/ConsentContext.jsx`. Ningún script no esencial se carga hasta que el usuario acepta (`client/src/utils/thirdPartyScripts.js`). Las preferencias se guardan server-side como cookie `HttpOnly; Secure; SameSite=Strict` (`server/src/utils/cookies.js`, `server/src/routes/consent.routes.js`).
2. **Rate limiting de IA** — `server/src/middleware/rateLimiter.js` (express-rate-limit + Redis, 10 req/min por IP o usuario autenticado). Responde `429` con `Retry-After`; el frontend muestra una cuenta regresiva (`client/src/hooks/useRateLimit.js`, `client/src/components/RateLimitAlert.jsx`).
3. **Guardrails de IA** — validación de entrada (Zod, `server/src/schemas/aiSchemas.js`), detección heurística de prompt injection (`server/src/services/promptGuard.js`), sanitización XSS (`server/src/middleware/sanitize.js`), y validación estricta de esquema de salida (`server/src/services/outputGuard.js`). En el frontend, botones de 👍/👎 y "Reportar error" (`client/src/components/ChatFeedback.jsx`).
4. **Disclaimer de IA** — `client/src/components/AIDisclaimer.jsx`, visible de forma persistente bajo el input del chat y en la pantalla de llamada por voz.
5. **Infraestructura** — Helmet (CSP, HSTS, X-Frame-Options) y CORS restringido en `server/src/middleware/security.js`; sanitización de todo el body de cada request antes de reenviarlo al proveedor de IA.
6. **Modo de Conversación por Voz (Hands-Free)** — ver sección dedicada abajo.
7. **Academic Asset Builder** — ver sección dedicada abajo.

## Modo de Conversación por Voz (Hands-Free)

Llamada continua y manos libres con la IA: el usuario pulsa **Start Conversation**, autoriza el micrófono una vez, y habla — sin botones de enviar, sin reiniciar el micrófono entre turnos.

### Voice Conversation Engine (`client/src/voice/`)

Módulo independiente y desacoplado, cada pieza intercambiable por su interfaz sin tocar el resto:

| Componente | Archivo | Responsabilidad |
|---|---|---|
| Microphone Manager | `MicrophoneManager.js` | `getUserMedia`, recuerda el permiso ya otorgado, libera el stream al colgar |
| Voice Activity Detection | `VoiceActivityDetector.js` | Detección de habla/silencio por energía (RMS) sobre el stream crudo — corre durante toda la llamada, incluida mientras la IA habla (es también el detector de interrupciones) |
| Speech Recognition (STT) | `SpeechRecognizer.js` | Envoltorio de `SpeechRecognition` nativo del navegador; reinicia automáticamente cuando el navegador corta la sesión por inactividad |
| Text To Speech (TTS) | `TextToSpeechEngine.js` | Envoltorio de `speechSynthesis`; encola oración por oración a medida que llegan del LLM (baja latencia) |
| Audio Playback | `AudioPlayback.js` | Cola de reproducción interrumpible para audio real (bytes) — punto de extensión listo para un TTS en la nube |
| Conversation Manager | `VoiceConversationEngine.js` | Máquina de estados que orquesta todo el flujo, interrupciones (barge-in) y comandos de voz |
| LLM Connector | `LLMConnector.js` | Streaming SSE hacia `/api/voice/converse`, abortable (el barge-in cancela también la generación en el servidor) |
| Session Manager | `SessionManager.js` | Persistencia del `sessionId` (para recargas), reconexión con backoff exponencial |
| Memory Manager (cliente) | `MemoryManager.js` | Caché de la transcripción para subtítulos y el comando "repite" |
| Detección de idioma | `languageDetect.js` | Heurística ligera por palabras funcionales para cambiar idioma de STT/TTS automáticamente |

Flujo: **Micrófono → VAD → STT → Conversation Manager → LLM (streaming) → TTS → Audio → vuelta a escuchar**, sin ciclos manuales de grabación.

### Interrupciones (barge-in)

El VAD corre continuamente incluso mientras la IA habla. Si detecta que el usuario vuelve a hablar (tras un margen de 300 ms para evitar falsos positivos por el arranque del audio), el motor: cancela inmediatamente la cola de TTS (`tts.cancel()`), aborta la solicitud de streaming en curso (`connector.interrupt()` → el `AbortSignal` llega hasta el servidor y detiene la generación del LLM, no solo el audio local) y vuelve a `Listening`.

Comandos de voz sin botones ("espera", "detente", "cancela", "repite", "continúa") se interceptan en `VoiceConversationEngine` antes de reenviar el turno al LLM.

### Backend (`server/src/services/voice/`, `server/src/routes/voice.routes.js`)

- `POST /api/voice/session` — crea una sesión (`mode`: general/language-learning/university, `language`, `personality`)
- `GET /api/voice/session/:id` — recupera el estado de sesión (usado en reconexión)
- `POST /api/voice/converse` — turno conversacional, streaming `text/event-stream`. Reutiliza los guardrails existentes (sanitización XSS global, `scanForInjection`, rate limiting propio vía `createVoiceRateLimiter`, 30 req/min por defecto — más alto que el chat de texto porque una llamada genera muchos más turnos por minuto).
- **Memoria de sesión** (`conversationSession.js`) en memoria de proceso (mover a Redis para despliegues multi-instancia, igual que el rate limiter). TTL de inactividad de 30 min.
- **Resumen automático** (`memoryManager.js`): al superar `VOICE_SUMMARIZE_AFTER_TURNS` (16 por defecto) turnos, los más antiguos se colapsan en un resumen vía LLM y solo se conservan los últimos `VOICE_KEEP_RECENT_TURNS` (6) verbatim — si el resumen falla, el historial completo se conserva en vez de perderse.
- **Prompts por modo** (`promptTemplates.js`): `language-learning` (corrige pronunciación/gramática, adapta dificultad, simula situaciones reales) y `university` (explica conceptos, resuelve ejercicios, evalúa comprensión) sin salir del flujo conversacional — instruyen al modelo a responder en frases cortas y naturales, aptas para ser leídas por TTS.

### Reconexión

Ante un fallo de red durante un turno, el motor pasa a `Reconnecting`, reintenta con backoff exponencial verificar que la sesión sigue viva en el servidor (`SessionManager.withRetry`) y, si lo logra, vuelve a `Listening` conservando el contexto; si no, pasa a `Disconnected` y el usuario debe pulsar **Start Conversation** de nuevo.

### Estados visibles (`VoiceCallScreen.jsx`, `VoiceStateOrb.jsx`)

`Listening` · `Thinking` · `Speaking` · `Interrupted` · `Reconnecting` · `Disconnected` — un único orbe animado, sin controles complejos.

### Escalabilidad

El desacoplamiento por interfaces (STT/TTS/transporte intercambiables detrás de una forma estable) es deliberado: añadir videollamadas, pantalla compartida, avatares, múltiples voces o traducción en tiempo real no requiere rediseñar `VoiceConversationEngine` — solo nuevas implementaciones detrás de las mismas interfaces (p. ej. `AudioPlayback.js` ya está listo para recibir bytes de un TTS en la nube en vez de `speechSynthesis`).

### Limitaciones conocidas

- STT/TTS usan las Web Speech APIs nativas del navegador (Chrome/Edge; sin soporte en Firefox y soporte parcial en Safari) — no requieren credenciales para probar el flujo completo, pero son swappable por un proveedor en la nube detrás de las mismas interfaces.
- La cancelación de eco depende de `echoCancellation` del navegador; en entornos sin auriculares puede haber falsos positivos ocasionales de barge-in por audio residual del propio TTS.
- La detección de idioma es heurística (palabras funcionales), no un modelo de identificación de idioma real.

## Academic Asset Builder (`server/src/asset-builder/`)

Los recursos educativos (imágenes, diagramas, audio, glosarios, flashcards, fórmulas, ejemplos...) se construyen **una sola vez, en tiempo de build**, y quedan persistidos permanentemente. Ningún estudiante provoca una búsqueda o generación en tiempo real — el runtime solo lee lo que este pipeline ya construyó y publicó.

> **Alcance de esta entrega:** este módulo es el *Academic Asset Builder* en sí (Analyzer → Planner → Providers → Validation → Persistence → Publication). Los builders anteriores en el flujo completo del enunciado (Content/Curriculum/Course/Lesson/Exercise/Assessment Builder) no existen todavía en este repositorio — el pipeline acepta como entrada el contenido de una lección ya autorada (ver `lessonContentSchema` en `schemas.js`) desde cualquier fuente que lo produzca.

### Flujo

**Analyzer → Planner → Providers (cadena de prioridad) → Validation → Persistence → Publication.** Nunca al revés, nunca durante la sesión del estudiante.

| Etapa | Archivo | Qué hace |
|---|---|---|
| Asset Analyzer | `analyzer/AssetAnalyzer.js` | Extrae tema, subtemas, conceptos, keywords, nivel, disciplina y tipo de contenido del **contenido completo** de la lección (no solo el título) — heurísticas deterministas (frecuencia de palabras, densidad de fórmulas/fechas) más una mejora opcional vía IA si hay proveedor configurado (`lib/aiEnhance.js`, con fallback automático a heurísticas puras) |
| Asset Planner | `planner/AssetPlanner.js` + `planner/rules.js` | Decide qué recursos necesita la lección según disciplina/tipo de contenido — nunca asume fotografías por defecto. Math pide fórmulas/ejemplos/diagramas, nunca fotos; historia pide timeline + fotos históricas; idiomas pide audio de pronunciación + flashcards |
| Asset Providers | `providers/*.js` | Cada proveedor implementa la misma interfaz (`AssetProvider.find()`) — intercambiables sin tocar el resto del pipeline |
| Validation | `validation/AssetValidator.js` | Formato, resolución (lectura real de dimensiones desde los magic bytes de PNG/JPEG/GIF/WebP/SVG, sin dependencias), licencia, relevancia (solapamiento de keywords), duplicados (SHA-256), puntuación de calidad/educativa |
| Persistence | `persistence/AssetLibrary.js` | Escribe la biblioteca versionada en disco |
| Publication | `persistence/AssetLibrary.js` (`publishVersion`) | Actualiza el puntero `current.json` y el índice de reutilización — separado de Persistence a propósito |

### Asset Providers y prioridad de recursos

Orden fijo (`providers/index.js`, `createDefaultProviderChain`): **biblioteca local → repositorio persistido → recursos educativos abiertos → Wikimedia Commons → Google Images → generación mediante IA.** Un proveedor solo se consulta si los anteriores no resolvieron la cantidad pedida.

| Proveedor | Red | Qué produce |
|---|---|---|
| `LocalLibraryProvider` | No | Reutiliza un asset ya publicado (de esta lección o de cualquier otra) antes de crear uno nuevo |
| `DiagramProvider` | No | Genera Mermaid/SVG real (mapa conceptual, timeline, diagrama relacional) a partir del análisis — nunca fabrica datos que el análisis no produjo |
| `TextResourceProvider` | No | Glosario, flashcards, fórmulas y ejemplos extraídos textualmente del cuerpo de la lección (oraciones reales que contienen cada término, expresiones con `=` detectadas por regex, secciones cuyo encabezado dice "ejemplo") — nunca inventa definiciones |
| `OpenEducationalResourcesProvider` | Sí (opcional) | Catálogo OER genérico vía `ASSET_OER_BASE_URL` |
| `WikimediaCommonsProvider` | Sí | API real de Wikimedia Commons (búsqueda + `imageinfo`), filtra por licencia (`CC0`/`CC-BY`/`CC-BY-SA`/dominio público) antes de aceptar un candidato |
| `GoogleImagesProvider` | Sí (opcional) | Google Programmable Search restringido a resultados con licencia reutilizable, vía `ASSET_GOOGLE_CSE_API_KEY`/`ASSET_GOOGLE_CSE_ID` |
| `AIGenerationProvider` | Sí (opcional) | Último recurso: genera una imagen vía API tipo OpenAI Images, vía `ASSET_IMAGE_GEN_API_KEY`/`BASE_URL` |
| `AudioProvider` | Sí (opcional) | TTS de build-time para pronunciaciones/lecturas, vía `ASSET_TTS_API_KEY`/`BASE_URL` |

Todo proveedor externo sin configurar devuelve `[]` (no candidatos) en vez de fallar el build — el pipeline reporta el plan item como `unresolved` para seguimiento humano en lugar de bloquear la publicación del resto de la lección.

### Persistencia y versionado

```
academy/<discipline>/<course>/<lesson>/
  current.json                 <- puntero a la versión publicada
  versions/
    v1/ content.json, metadata.json, assets/{images,videos,audio,diagrams,illustrations}/
    v2/ ...
academy/_index.json             <- índice de reutilización de todos los assets publicados
```

Reconstruir una lección crea una nueva versión (`v2`, `v3`...) sin tocar las anteriores ni ninguna otra lección — verificado: reconstruir `algebra-linear-equations` generó `v2` dejando `v1` intacto y sin modificar los `metadata.json` de otras lecciones. `ASSET_LIBRARY_ROOT` controla la ubicación (por defecto `academy/`, fuera de control de versiones — es un artefacto de build, no código fuente).

### Mantenimiento automático (`maintenance/assetMaintenance.js`)

Nunca se ejecuta durante la sesión de un estudiante ni está enlazado a la app Express — se invoca vía `npm run assets:maintain` (scheduler externo: cron, una Routine, un job de CI). Recorre el índice, verifica cada asset (`HEAD` para recursos remotos, `fs.access` para locales), y **reemplaza solo el asset afectado**: re-analiza el contenido real de la lección (no una copia parcial de metadata), vuelve a planear, y reintenta la cadena de proveedores para ese único recurso. Verificado en vivo: se borró manualmente un archivo publicado, la primera pasada expuso dos bugs reales (un candidato de reutilización local apuntando a un archivo ya inexistente, y un rechazo por "duplicado" contra el propio asset que se estaba reparando) — ambos corregidos, y una segunda pasada restauró el archivo correctamente con metadata actualizada.

### Servido de solo lectura (`server/src/routes/academy.routes.js`)

`GET /api/academy/:discipline/:course/:lesson` y `GET /api/academy/file/*` son las **únicas** rutas que un estudiante toca — ambas son lecturas de filesystem sobre lo ya publicado, nunca disparan una búsqueda o generación. `GET /api/academy/file/*` solo sirve archivos de la versión **actualmente publicada** de cada lección (verificado: pedir una versión no publicada devuelve `404`) y rechaza path traversal (verificado con `%2e%2e`).

### CLI (content authors, nunca estudiantes)

```bash
cd server
npm run assets:build -- path/to/lesson.json   # construye y publica una lección
npm run assets:build -- path/to/lesson.json --no-publish   # construye sin publicar
npm run assets:maintain                        # barrido de mantenimiento
```

Tres lecciones de ejemplo en `src/asset-builder/examples/` (álgebra, biología, historia) demuestran que el Planner efectivamente ramifica por disciplina: álgebra nunca pide fotografías (fórmulas/ejemplos/tabla, generados y extraídos del propio texto), biología pide ilustración científica + diagrama, historia pide timeline + fotos de época.

### Metadata

Cada asset persistido incluye (`schemas.js`, `assetMetadataSchema`, validado con Zod antes de escribirse): `id`, `lesson_id`, `course_id`, `language`, `resource_type`, `provider`, `version`, `license`, `keywords`, `created_at`, `updated_at`, `quality_score`, `educational_score`, más los campos prácticos que la validación y el servido necesitan (`format`, `file_path`, `checksum_sha256`, `relevance_score`, dimensiones).

### Escalabilidad

El índice de reutilización (`academy/_index.json`) es lo que mantiene el volumen de llamadas externas plano al crecer el catálogo — una búsqueda de reutilización es una lectura local, no una llamada a un servicio. A escala de "millones de recursos" ese archivo se reemplaza por una base de datos/índice real (Postgres + búsqueda por keywords, Elasticsearch, ...) sin cambiar nada río arriba, porque providers y pipeline solo llaman a `queryIndex`/`isDuplicateChecksum`/`upsertLessonEntries`.

### Limitaciones conocidas

- El entorno de pruebas de esta sesión bloquea el egreso de red hacia hosts externos (incluido Wikimedia Commons, confirmado con `403` del proxy) — `WikimediaCommonsProvider`, `GoogleImagesProvider`, `AIGenerationProvider` y `AudioProvider` están implementados contra las APIs reales pero no se pudieron ejercitar en vivo aquí; sí se verificó su degradación correcta (log + `[]` + el pipeline continúa) cuando no responden.
- `OpenEducationalResourcesProvider`/`GoogleImagesProvider`/`AIGenerationProvider`/`AudioProvider` requieren credenciales propias (`ASSET_OER_*`, `ASSET_GOOGLE_CSE_*`, `ASSET_IMAGE_GEN_*`, `ASSET_TTS_*`) — sin configurar, simplemente no aportan candidatos.
- El índice basado en JSON plano es apropiado para el alcance de este repo, no para producción a gran escala (ver "Escalabilidad").

## Requisitos

- Node.js ≥ 18
- Redis (para el store distribuido de rate limiting)

## Cómo ejecutar

### Backend

```bash
cd server
cp .env.example .env   # completa AI_PROVIDER_API_KEY/BASE_URL con tu proveedor real
npm install
npm run dev             # http://localhost:4000
```

Sin `AI_PROVIDER_API_KEY`/`AI_PROVIDER_BASE_URL` configurados, el servidor usa una respuesta simulada (`[dev-mock]`) para poder probar todo el pipeline localmente sin credenciales reales.

### Frontend

```bash
cd client
npm install
npm run dev             # http://localhost:5173 (proxy a /api -> localhost:4000)
```

## Verificación manual realizada

- `GET /api/health` → `200`
- `GET/POST/DELETE /api/consent` → guarda y lee preferencias vía cookie `HttpOnly`
- `POST /api/ai/chat` con texto normal → `200` con respuesta validada por esquema
- `POST /api/ai/chat` con `<script>...</script>` → contenido sanitizado antes de llegar al proveedor
- `POST /api/ai/chat` con "ignore all previous instructions..." → `422 input_rejected`
- 11 solicitudes rápidas a `/api/ai/chat` → a partir del límite, `429` con `Retry-After` y `retryAfterSeconds`
- `POST /api/voice/session` + `POST /api/voice/converse` → streaming SSE completo, sesión guarda ambos turnos (`turnCount`)
- Corte de conexión a mitad del streaming (barge-in simulado) → el turno se guarda como `[interrupted by user]`, sin errores en el servidor
- 9 turnos consecutivos en una sesión de voz → resumen automático activado al superar el umbral, `turnCount` se reduce correctamente y el historial no se pierde
- `GET /api/voice/session/:id` con id inexistente → `404 session_not_found`
- `npm run build` del cliente (Vite) compila sin errores
- `npm run assets:build` sobre 3 lecciones de ejemplo (álgebra/biología/historia) → cada una construye y publica assets distintos según su disciplina, con gaps honestamente reportados en `unresolved` cuando un proveedor no está disponible
- Reconstruir la misma lección → nueva versión (`v2`) reutiliza el 100% de los assets vía `local-library` en vez de regenerarlos; `v1` y las demás lecciones quedan intactas (verificado por timestamps de archivo)
- `GET /api/academy/:discipline/:course/:lesson` y `GET /api/academy/file/*` → sirven contenido real ya publicado; `404` para lección/versión inexistente, `400` para path traversal
- Borrado manual de un asset publicado + `npm run assets:maintain` → detectado, reparado (regenerado desde el contenido real de la lección) y metadata actualizada, sin tocar otros assets

## Notas para producción

- Conecta `callAiProvider` (`server/src/services/aiClient.js`) a tu proveedor real de IA.
- Sustituye el almacén en memoria de `server/src/routes/feedback.routes.js` por una base de datos persistente.
- Añade autenticación real (el middleware `optionalAuth` ya soporta JWT `Bearer` para asociar el rate limit a usuarios autenticados).
- Sirve el frontend detrás de HTTPS: `Secure` en cookies y `HSTS` solo son efectivos sobre TLS.
- Configura las credenciales de los proveedores externos del Academic Asset Builder (`ASSET_OER_*`, `ASSET_GOOGLE_CSE_*`, `ASSET_IMAGE_GEN_*`, `ASSET_TTS_*`) y agenda `npm run assets:maintain` en un scheduler externo (cron/Routine).
- Reemplaza `academy/_index.json` por una base de datos real al acercarte a los volúmenes de catálogo descritos en "Escalabilidad".
