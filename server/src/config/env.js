import 'dotenv/config';

function required(name, fallback) {
  const value = process.env[name] ?? fallback;
  if (value === undefined) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const env = {
  nodeEnv: process.env.NODE_ENV || 'development',
  port: Number(process.env.PORT || 4000),
  clientOrigin: required('CLIENT_ORIGIN', 'http://localhost:5173'),
  jwtSecret: required('JWT_SECRET', 'dev-secret-do-not-use-in-prod'),
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  aiRateLimitWindowMs: Number(process.env.AI_RATE_LIMIT_WINDOW_MS || 60_000),
  aiRateLimitMax: Number(process.env.AI_RATE_LIMIT_MAX || 10),
  aiProviderApiKey: process.env.AI_PROVIDER_API_KEY || '',
  aiProviderBaseUrl: process.env.AI_PROVIDER_BASE_URL || '',
  cookieDomain: process.env.COOKIE_DOMAIN || 'localhost',
  isProduction: (process.env.NODE_ENV || 'development') === 'production',

  // Voice Conversation Engine
  voiceRateLimitWindowMs: Number(process.env.VOICE_RATE_LIMIT_WINDOW_MS || 60_000),
  voiceRateLimitMax: Number(process.env.VOICE_RATE_LIMIT_MAX || 30),
  voiceSessionTtlMs: Number(process.env.VOICE_SESSION_TTL_MS || 30 * 60_000), // 30 min idle expiry
  voiceSummarizeAfterTurns: Number(process.env.VOICE_SUMMARIZE_AFTER_TURNS || 16),
  voiceKeepRecentTurns: Number(process.env.VOICE_KEEP_RECENT_TURNS || 6),
};
