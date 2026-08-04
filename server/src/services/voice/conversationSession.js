import { randomUUID } from 'node:crypto';
import { env } from '../../config/env.js';
import { summarizeIfNeeded } from './memoryManager.js';
import { SUPPORTED_MODES } from './promptTemplates.js';

/**
 * In-memory session store — sufficient for a single server instance. For a
 * multi-instance deployment, move this to Redis (same store already used for
 * rate limiting) keyed by sessionId so any instance can serve a reconnecting
 * client.
 */
const sessions = new Map();

export function createSession({ mode = 'general', language = 'es', personality } = {}) {
  const id = randomUUID();
  const now = Date.now();
  const session = {
    id,
    mode: SUPPORTED_MODES.includes(mode) ? mode : 'general',
    language,
    personality,
    history: [], // [{ role: 'user' | 'assistant', content, ts }]
    summary: null,
    createdAt: now,
    lastActiveAt: now,
  };
  sessions.set(id, session);
  return session;
}

export function getSession(id) {
  const session = sessions.get(id);
  if (!session) return null;
  if (Date.now() - session.lastActiveAt > env.voiceSessionTtlMs) {
    sessions.delete(id);
    return null;
  }
  return session;
}

export function touchSession(session) {
  session.lastActiveAt = Date.now();
}

export async function appendTurn(session, role, content) {
  session.history.push({ role, content, ts: Date.now() });
  touchSession(session);
  await summarizeIfNeeded(session);
}

export function setSessionLanguage(session, language) {
  session.language = language;
}

export function endSession(id) {
  sessions.delete(id);
}

export function toClientView(session) {
  return {
    sessionId: session.id,
    mode: session.mode,
    language: session.language,
    summary: session.summary,
    turnCount: session.history.length,
  };
}

// Periodic sweep so idle sessions don't grow memory unbounded. unref() so
// this timer never keeps the process alive on its own (tests, shutdown).
setInterval(() => {
  const now = Date.now();
  for (const [id, session] of sessions) {
    if (now - session.lastActiveAt > env.voiceSessionTtlMs) sessions.delete(id);
  }
}, 5 * 60_000).unref();
