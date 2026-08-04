import express from 'express';
import cookieParser from 'cookie-parser';
import { securityHeaders, corsPolicy } from './middleware/security.js';
import { sanitizeBody } from './middleware/sanitize.js';
import { optionalAuth } from './middleware/auth.js';
import { aiRouter } from './routes/ai.routes.js';
import { feedbackRouter } from './routes/feedback.routes.js';
import { consentRouter } from './routes/consent.routes.js';
import { voiceRouter } from './routes/voice.routes.js';
import { academyRouter } from './routes/academy.routes.js';

export function createApp() {
  const app = express();

  // Trust the first proxy hop (load balancer) so req.ip reflects the real
  // client IP — required for correct per-IP rate limiting behind a proxy.
  app.set('trust proxy', 1);

  app.use(securityHeaders);
  app.use(corsPolicy);
  app.use(express.json({ limit: '100kb' }));
  app.use(cookieParser());
  app.use(sanitizeBody);
  app.use(optionalAuth);

  app.get('/api/health', (_req, res) => res.json({ ok: true }));

  app.use('/api/consent', consentRouter);
  app.use('/api/ai', aiRouter);
  app.use('/api/feedback', feedbackRouter);
  app.use('/api/voice', voiceRouter);
  app.use('/api/academy', academyRouter);

  // Centralized error handler — never leak stack traces to the client.
  app.use((err, _req, res, _next) => {
    console.error('[unhandled]', err);
    res.status(500).json({ error: 'internal_error', message: 'Something went wrong.' });
  });

  return app;
}
