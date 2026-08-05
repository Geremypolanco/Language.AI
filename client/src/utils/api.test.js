import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, RateLimitError } from './api.js';

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

describe('apiFetch', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test('resolves with the parsed JSON body on success', async () => {
    fetch.mockResolvedValue(jsonResponse({ ok: true }));
    const result = await apiFetch('/health');
    expect(result).toEqual({ ok: true });
  });

  test('always sends credentials so the consent cookie round-trips', async () => {
    fetch.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch('/consent');
    const [, options] = fetch.mock.calls[0];
    expect(options.credentials).toBe('include');
  });

  test('prefixes the path with the API base URL', async () => {
    fetch.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch('/ai/chat');
    const [url] = fetch.mock.calls[0];
    expect(url).toBe('/api/ai/chat');
  });

  test('merges caller-supplied headers with the JSON content-type default', async () => {
    fetch.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch('/ai/chat', { headers: { 'X-Custom': 'yes' } });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(options.headers['X-Custom']).toBe('yes');
  });

  test('throws a typed RateLimitError with the retryAfterSeconds from the response body', async () => {
    fetch.mockResolvedValue(
      jsonResponse({ retryAfterSeconds: 42, message: 'slow down' }, { status: 429, headers: { 'Retry-After': '99' } })
    );
    await expect(apiFetch('/ai/chat')).rejects.toMatchObject({
      name: 'RateLimitError',
      retryAfterSeconds: 42,
      message: 'slow down',
    });
  });

  test('falls back to the Retry-After header when the body omits retryAfterSeconds', async () => {
    fetch.mockResolvedValue(jsonResponse({}, { status: 429, headers: { 'Retry-After': '30' } }));
    await expect(apiFetch('/ai/chat')).rejects.toMatchObject({ retryAfterSeconds: 30 });
  });

  test('falls back to 60s when neither the body nor the header carry a retry time', async () => {
    fetch.mockResolvedValue(jsonResponse({}, { status: 429 }));
    await expect(apiFetch('/ai/chat')).rejects.toMatchObject({ retryAfterSeconds: 60 });
  });

  test('a caught RateLimitError instance passes an instanceof check', async () => {
    fetch.mockResolvedValue(jsonResponse({}, { status: 429 }));
    await expect(apiFetch('/ai/chat')).rejects.toBeInstanceOf(RateLimitError);
  });

  test('throws a generic Error with the server message for other non-ok statuses', async () => {
    fetch.mockResolvedValue(jsonResponse({ message: 'nope' }, { status: 400 }));
    await expect(apiFetch('/consent')).rejects.toThrow('nope');
  });

  test('falls back to a status-based message when the error body has none', async () => {
    fetch.mockResolvedValue(new Response('not json', { status: 500 }));
    await expect(apiFetch('/consent')).rejects.toThrow('Request failed with status 500');
  });
});
