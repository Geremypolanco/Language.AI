const API_BASE = '/api';

export class RateLimitError extends Error {
  constructor(message, retryAfterSeconds) {
    super(message);
    this.name = 'RateLimitError';
    this.retryAfterSeconds = retryAfterSeconds;
  }
}
export class SessionExpiredError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SessionExpiredError';
  }
}
export class InputRejectedError extends Error {
  constructor(message) {
    super(message);
    this.name = 'InputRejectedError';
  }
}

/**
 * Talks to the server's voice endpoints (session lifecycle + streaming
 * conversation turns). Isolated behind this class so ConversationManager
 * never touches fetch/SSE parsing directly — only the transport, not the
 * conversation logic, needs to change if the backend moves to WebSockets.
 */
export class LLMConnector {
  #controller = null;

  async createSession({ mode, language, personality }) {
    const res = await fetch(`${API_BASE}/voice/session`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, language, personality }),
    });
    if (!res.ok) throw new Error(`Failed to create voice session (${res.status})`);
    return res.json();
  }

  async getSession(sessionId) {
    const res = await fetch(`${API_BASE}/voice/session/${sessionId}`, { credentials: 'include' });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch voice session (${res.status})`);
    return res.json();
  }

  async endSession(sessionId) {
    await fetch(`${API_BASE}/voice/session/${sessionId}`, { method: 'DELETE', credentials: 'include' }).catch(() => {});
  }

  /**
   * Streams one conversational turn, calling `onDelta(text)` per token
   * chunk and resolving with the final `done` payload. Call interrupt() at
   * any point (e.g. on barge-in) to abort the underlying request
   * immediately — this stops server-side generation too, not just local
   * audio playback.
   */
  async converse({ sessionId, message, language }, { onDelta } = {}) {
    // Kept alive for the *entire* call (headers + full body stream), not just
    // until fetch()'s promise settles — otherwise interrupt() would have
    // nothing left to abort once token deltas start arriving, which is
    // exactly when barge-in needs to fire.
    const controller = new AbortController();
    this.#controller = controller;

    try {
      const response = await fetch(`${API_BASE}/voice/converse`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, message, language }),
        signal: controller.signal,
      });

      if (response.status === 429) {
        const body = await response.json().catch(() => ({}));
        throw new RateLimitError(body.message || 'Rate limited', body.retryAfterSeconds ?? 30);
      }
      if (response.status === 404) {
        throw new SessionExpiredError('Voice session expired or not found.');
      }
      if (response.status === 422) {
        throw new InputRejectedError('Input rejected by safety filters.');
      }
      if (!response.ok || !response.body) {
        throw new Error(`Voice conversation request failed (${response.status})`);
      }

      return await this.#consumeStream(response, onDelta);
    } catch (err) {
      if (err.name === 'AbortError') return { interrupted: true };
      throw err;
    } finally {
      if (this.#controller === controller) this.#controller = null;
    }
  }

  async #consumeStream(response, onDelta) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let donePayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        let payload;
        try {
          payload = JSON.parse(trimmed.slice(5).trim());
        } catch {
          continue;
        }
        if (payload.type === 'delta') onDelta?.(payload.text);
        else if (payload.type === 'done') donePayload = payload;
        else if (payload.type === 'error') throw new Error(payload.message);
      }
    }

    return donePayload || { interrupted: true };
  }

  /** Aborts the in-flight converse() request, if any — the barge-in primitive on the network side. */
  interrupt() {
    this.#controller?.abort();
    this.#controller = null;
  }
}
