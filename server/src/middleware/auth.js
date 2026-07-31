import jwt from 'jsonwebtoken';
import { env } from '../config/env.js';

/**
 * Optional authentication: if a valid Bearer token is present, attaches
 * req.user so downstream middleware (e.g. the rate limiter) can key off the
 * authenticated user instead of the raw IP. Absence of a token is not an
 * error here — routes that require auth should enforce that separately.
 */
export function optionalAuth(req, _res, next) {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) return next();

  const token = header.slice('Bearer '.length);
  try {
    const payload = jwt.verify(token, env.jwtSecret);
    req.user = { id: payload.sub };
  } catch {
    // Invalid/expired token: proceed unauthenticated rather than failing the request.
  }
  next();
}
