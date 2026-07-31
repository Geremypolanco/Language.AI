import rateLimit from 'express-rate-limit';
import { RedisStore } from 'rate-limit-redis';
import { getRedisClient } from '../utils/redisClient.js';
import { env } from '../config/env.js';

/**
 * Rate limit key: authenticated user id when available (req.user is set by
 * the optional auth middleware upstream), otherwise the client IP. This keeps
 * shared-IP users (offices, NAT) from being punished for one heavy user once
 * they authenticate, while still bounding anonymous traffic per IP.
 */
function rateLimitKey(req) {
  return req.user?.id ? `user:${req.user.id}` : `ip:${req.ip}`;
}

/**
 * Rate limiter for AI-consuming routes: 10 requests/minute per IP or
 * authenticated user, backed by Redis so the limit is enforced consistently
 * across all server instances.
 */
export async function createAiRateLimiter() {
  const redisClient = await getRedisClient();

  return rateLimit({
    windowMs: env.aiRateLimitWindowMs, // 60_000 by default
    max: env.aiRateLimitMax, // 10 by default
    standardHeaders: true, // adds RateLimit-* headers
    legacyHeaders: false,
    keyGenerator: rateLimitKey,
    store: new RedisStore({
      sendCommand: (...args) => redisClient.sendCommand(args),
      prefix: 'rl:ai:',
    }),
    handler: (req, res) => {
      const resetMs = req.rateLimit?.resetTime ? req.rateLimit.resetTime.getTime() - Date.now() : env.aiRateLimitWindowMs;
      const retryAfterSeconds = Math.max(1, Math.ceil(resetMs / 1000));
      res.set('Retry-After', String(retryAfterSeconds));
      res.status(429).json({
        error: 'rate_limited',
        message: 'Too many AI requests. Please wait before retrying.',
        retryAfterSeconds,
        limit: env.aiRateLimitMax,
        windowSeconds: env.aiRateLimitWindowMs / 1000,
      });
    },
  });
}
