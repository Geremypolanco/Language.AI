import { describe, test, expect, vi, beforeEach } from 'vitest';
import { SessionManager } from './SessionManager.js';

function fakeConnector({ getSession = vi.fn() } = {}) {
  return { getSession };
}

beforeEach(() => {
  sessionStorage.clear();
});

describe('SessionManager persistence', () => {
  test('save() then load() round-trips the session shape', () => {
    const manager = new SessionManager(fakeConnector());
    manager.save({ sessionId: 'abc123', mode: 'general', language: 'en' });
    expect(manager.load()).toEqual({ sessionId: 'abc123', mode: 'general', language: 'en' });
  });

  test('load() returns null when nothing was saved', () => {
    const manager = new SessionManager(fakeConnector());
    expect(manager.load()).toBeNull();
  });

  test('load() returns null instead of throwing on corrupted storage', () => {
    sessionStorage.setItem('languageai_voice_session', 'not-json{{{');
    const manager = new SessionManager(fakeConnector());
    expect(manager.load()).toBeNull();
  });

  test('clear() removes the saved session', () => {
    const manager = new SessionManager(fakeConnector());
    manager.save({ sessionId: 'abc123', mode: 'general', language: 'en' });
    manager.clear();
    expect(manager.load()).toBeNull();
  });
});

describe('SessionManager.restore', () => {
  test('returns null when nothing was ever saved', async () => {
    const manager = new SessionManager(fakeConnector());
    expect(await manager.restore()).toBeNull();
  });

  test('returns the remote session state when the server still has it', async () => {
    const getSession = vi.fn().mockResolvedValue({ sessionId: 'abc123', turnCount: 4 });
    const manager = new SessionManager(fakeConnector({ getSession }));
    manager.save({ sessionId: 'abc123', mode: 'general', language: 'en' });

    const restored = await manager.restore();
    expect(restored).toEqual({ sessionId: 'abc123', turnCount: 4 });
    expect(getSession).toHaveBeenCalledWith('abc123');
  });

  test('clears the saved session and returns null when the server no longer knows it (404)', async () => {
    const getSession = vi.fn().mockRejectedValue(new Error('not found'));
    const manager = new SessionManager(fakeConnector({ getSession }));
    manager.save({ sessionId: 'gone', mode: 'general', language: 'en' });

    expect(await manager.restore()).toBeNull();
    expect(manager.load()).toBeNull();
  });
});

describe('SessionManager.withRetry', () => {
  test('returns the result immediately on first success without retrying', async () => {
    const manager = new SessionManager(fakeConnector());
    const fn = vi.fn().mockResolvedValue('ok');
    const result = await manager.withRetry(fn, { retries: 4, baseDelayMs: 0 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test('retries on failure and eventually succeeds', async () => {
    const manager = new SessionManager(fakeConnector());
    let attempts = 0;
    const fn = vi.fn().mockImplementation(() => {
      attempts += 1;
      if (attempts < 3) return Promise.reject(new Error('transient'));
      return Promise.resolve('recovered');
    });
    const result = await manager.withRetry(fn, { retries: 5, baseDelayMs: 0 });
    expect(result).toBe('recovered');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  test('rejects with the last error once retries are exhausted', async () => {
    const manager = new SessionManager(fakeConnector());
    const fn = vi.fn().mockRejectedValue(new Error('permanent failure'));
    await expect(manager.withRetry(fn, { retries: 3, baseDelayMs: 0 })).rejects.toThrow('permanent failure');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  test('calls onAttempt with the current attempt number and total retries', async () => {
    const manager = new SessionManager(fakeConnector());
    const onAttempt = vi.fn();
    const fn = vi.fn().mockResolvedValue('ok');
    await manager.withRetry(fn, { retries: 4, baseDelayMs: 0, onAttempt });
    expect(onAttempt).toHaveBeenCalledWith(1, 4);
  });
});
