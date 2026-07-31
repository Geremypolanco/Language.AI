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
4. **Disclaimer de IA** — `client/src/components/AIDisclaimer.jsx`, visible de forma persistente bajo el input del chat.
5. **Infraestructura** — Helmet (CSP, HSTS, X-Frame-Options) y CORS restringido en `server/src/middleware/security.js`; sanitización de todo el body de cada request antes de reenviarlo al proveedor de IA.

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
- `npm run build` del cliente (Vite) compila sin errores

## Notas para producción

- Conecta `callAiProvider` (`server/src/services/aiClient.js`) a tu proveedor real de IA.
- Sustituye el almacén en memoria de `server/src/routes/feedback.routes.js` por una base de datos persistente.
- Añade autenticación real (el middleware `optionalAuth` ya soporta JWT `Bearer` para asociar el rate limit a usuarios autenticados).
- Sirve el frontend detrás de HTTPS: `Secure` en cookies y `HSTS` solo son efectivos sobre TLS.
