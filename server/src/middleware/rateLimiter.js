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
 * Generic Redis-backed rate limiter factory. Every AI-consuming surface
 * (typed chat, voice turns, ...) gets its own bucket via `prefix` so one
 * doesn't starve the other, while sharing the same Redis connection, key
 * strategy, and 429/Retry-After response shape.
 */
async function createRateLimiter({ windowMs, max, prefix, message }) {
  const redisClient = await getRedisClient();

  return rateLimit({
    windowMs,
    max,
    standardHeaders: true, // adds RateLimit-* headers
    legacyHeaders: false,
    keyGenerator: rateLimitKey,
    store: new RedisStore({
      sendCommand: (...args) => redisClient.sendCommand(args),
      prefix,
    }),
    handler: (req, res) => {
      const resetMs = req.rateLimit?.resetTime ? req.rateLimit.resetTime.getTime() - Date.now() : windowMs;
      const retryAfterSeconds = Math.max(1, Math.ceil(resetMs / 1000));
      res.set('Retry-After', String(retryAfterSeconds));
      res.status(429).json({
        error: 'rate_limited',
        message,
        retryAfterSeconds,
        limit: max,
        windowSeconds: windowMs / 1000,
      });
    },
  });
}

/** 10 requests/minute per IP or authenticated user on the typed AI chat endpoint. */
export function createAiRateLimiter() {
  return createRateLimiter({
    windowMs: env.aiRateLimitWindowMs,
    max: env.aiRateLimitMax,
    prefix: 'rl:ai:',
    message: 'Too many AI requests. Please wait before retrying.',
  });
}

/**
 * Higher ceiling for the voice conversation endpoint: a single spoken
 * exchange (listen -> transcript -> reply) is one request but a natural
 * back-and-forth call produces many more turns per minute than typed chat.
 */
export function createVoiceRateLimiter() {
  return createRateLimiter({
    windowMs: env.voiceRateLimitWindowMs,
    max: env.voiceRateLimitMax,
    prefix: 'rl:voice:',
    message: 'Too many conversation turns. Please wait a moment before continuing.',
  });
}
