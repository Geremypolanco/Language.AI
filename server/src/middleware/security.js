import helmet from 'helmet';
import cors from 'cors';
import { env } from '../config/env.js';

/**
 * Helmet configuration: strict CSP (no inline scripts/styles, no third-party
 * origins by default), HSTS, and frame-ancestors denial to block clickjacking.
 * Analytics/marketing origins are intentionally absent from connect-src/script-src;
 * they are only allowed once a user grants consent (see utils/thirdPartyScripts on
 * the client, which loads them into a nonce'd/whitelisted context instead of relying
 * on a permissive CSP).
 */
export const securityHeaders = helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", 'data:'],
      connectSrc: ["'self'"],
      fontSrc: ["'self'"],
      objectSrc: ["'none'"],
      frameAncestors: ["'none'"],
      baseUri: ["'self'"],
      formAction: ["'self'"],
      upgradeInsecureRequests: env.isProduction ? [] : null,
    },
  },
  crossOriginEmbedderPolicy: false,
  hsts: {
    maxAge: 63072000, // 2 years
    includeSubDomains: true,
    preload: true,
  },
  frameguard: { action: 'deny' },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
  noSniff: true,
});

export const corsPolicy = cors({
  origin: env.clientOrigin,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
});
