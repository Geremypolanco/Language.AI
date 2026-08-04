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

  // Academic Asset Builder — external providers (all optional; an
  // unconfigured provider returns no candidates instead of failing the build)
  assetLibraryRoot: process.env.ASSET_LIBRARY_ROOT || 'academy',
  wikimediaUserAgent:
    process.env.ASSET_WIKIMEDIA_USER_AGENT || 'Language.AI-AcademicAssetBuilder/1.0 (educational content pipeline)',
  oerBaseUrl: process.env.ASSET_OER_BASE_URL || '',
  oerApiKey: process.env.ASSET_OER_API_KEY || '',
  googleCseApiKey: process.env.ASSET_GOOGLE_CSE_API_KEY || '',
  googleCseId: process.env.ASSET_GOOGLE_CSE_ID || '',
  imageGenApiKey: process.env.ASSET_IMAGE_GEN_API_KEY || '',
  imageGenBaseUrl: process.env.ASSET_IMAGE_GEN_BASE_URL || '',
  ttsApiKey: process.env.ASSET_TTS_API_KEY || '',
  ttsBaseUrl: process.env.ASSET_TTS_BASE_URL || '',
};
