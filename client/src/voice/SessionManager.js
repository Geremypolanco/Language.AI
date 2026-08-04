const STORAGE_KEY = 'languageai_voice_session';

/**
 * Persists the active call's session id across reloads/reconnects
 * (sessionStorage — scoped to the tab, doesn't need manual cleanup) and
 * provides the retry-with-backoff helper used to recover from dropped
 * connections without losing conversation continuity.
 */
export class SessionManager {
  constructor(connector) {
    this.connector = connector;
  }

  save({ sessionId, mode, language }) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ sessionId, mode, language }));
  }

  load() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
      return null;
    }
  }

  clear() {
    sessionStorage.removeItem(STORAGE_KEY);
  }

  /** Returns the remembered session's server-side state, or null if it no longer exists. */
  async restore() {
    const saved = this.load();
    if (!saved?.sessionId) return null;
    const remote = await this.connector.getSession(saved.sessionId).catch(() => null);
    if (!remote) {
      this.clear();
      return null;
    }
    return remote;
  }

  /** Retries `fn` with exponential backoff. Rejects with the last error once retries are exhausted. */
  async withRetry(fn, { retries = 4, baseDelayMs = 1000, onAttempt } = {}) {
    let attempt = 0;
    let lastError;
    while (attempt < retries) {
      try {
        onAttempt?.(attempt + 1, retries);
        return await fn();
      } catch (err) {
        lastError = err;
        attempt += 1;
        if (attempt >= retries) break;
        await new Promise((resolve) => setTimeout(resolve, baseDelayMs * 2 ** (attempt - 1)));
      }
    }
    throw lastError;
  }
}
