import http from 'node:http';
import { createApp } from '../../../src/app.js';
import { closeRedisClient, getRedisClient } from '../../../src/utils/redisClient.js';

/**
 * Boots the *real* Express app (same createApp() the production entrypoint
 * uses) on an ephemeral port for integration tests to hit over HTTP — no
 * mocking of Express itself, only the AI provider stays in its dev-mock
 * fallback (no API key set in the test environment).
 */
export async function startTestServer() {
  const app = createApp();
  const server = http.createServer(app);
  await new Promise((resolve) => server.listen(0, resolve));
  const { port } = server.address();
  return { server, baseUrl: `http://127.0.0.1:${port}` };
}

export async function stopTestServer(server) {
  await new Promise((resolve) => server.close(resolve));
  // The app's rate limiters share one long-lived Redis connection; without
  // this the socket keeps the event loop alive and `node --test` hangs
  // waiting for this file's process to exit even after all tests finish.
  await closeRedisClient();
}

/**
 * Rate-limit counters live in real Redis and outlive any single test run, so
 * a suite that asserts exact request counts against a rate limit (e.g. "the
 * 5th request should NOT be limited yet") is flaky unless it starts from a
 * clean slate. Deletes every key under `prefix` before such a suite runs.
 */
export async function resetRateLimitState(prefix) {
  const client = await getRedisClient();
  const keys = await client.keys(`${prefix}*`);
  if (keys.length > 0) await client.del(keys);
}

/** Minimal cookie jar so integration tests can carry HttpOnly cookies (e.g. consent) across requests, the way a browser would. */
export class CookieJar {
  #cookies = new Map();

  capture(response) {
    for (const setCookie of response.headers.getSetCookie?.() ?? []) {
      const [pair] = setCookie.split(';');
      const [name, value] = pair.split('=');
      this.#cookies.set(name.trim(), value);
    }
  }

  header() {
    return [...this.#cookies.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
  }
}

/** fetch wrapper that automatically sends/captures cookies through a CookieJar. */
export async function fetchWithJar(url, options = {}, jar = new CookieJar()) {
  const headers = { ...options.headers };
  const cookieHeader = jar.header();
  if (cookieHeader) headers.Cookie = cookieHeader;

  const response = await fetch(url, { ...options, headers });
  jar.capture(response);
  return response;
}
