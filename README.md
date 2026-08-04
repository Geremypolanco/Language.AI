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

## Notas para producción

- Conecta `callAiProvider` (`server/src/services/aiClient.js`) a tu proveedor real de IA.
- Sustituye el almacén en memoria de `server/src/routes/feedback.routes.js` por una base de datos persistente.
- Añade autenticación real (el middleware `optionalAuth` ya soporta JWT `Bearer` para asociar el rate limit a usuarios autenticados).
- Sirve el frontend detrás de HTTPS: `Secure` en cookies y `HSTS` solo son efectivos sobre TLS.
