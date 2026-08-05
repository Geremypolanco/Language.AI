const BASE_URL = '/api';

export class RateLimitError extends Error {
  constructor(retryAfterSeconds, message) {
    super(message);
    this.name = 'RateLimitError';
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/**
 * Fetch wrapper shared by the whole app. Always sends credentials so the
 * HttpOnly consent cookie round-trips with the server, and translates a 429
 * into a typed RateLimitError the UI can render a countdown for instead of a
 * generic failure.
 */
export async function apiFetch(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    // Spread options first: credentials/headers below must win, otherwise a
    // caller-supplied `options.headers` (e.g. one extra header) would
    // replace the whole merged headers object and silently drop
    // Content-Type instead of adding to it.
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });

  if (response.status === 429) {
    const body = await response.json().catch(() => ({}));
    const retryAfterHeaderRaw = response.headers.get('Retry-After');
    // Number(null) is 0, not NaN — without the null check, a 429 with no
    // Retry-After header would compute a "retry in 0s" instead of falling
    // back to a sane default, inviting an immediate hammer-retry loop.
    const retryAfterHeader = retryAfterHeaderRaw === null ? NaN : Number(retryAfterHeaderRaw);
    const retryAfterSeconds = body.retryAfterSeconds ?? (Number.isFinite(retryAfterHeader) ? retryAfterHeader : 60);
    throw new RateLimitError(retryAfterSeconds, body.message || 'Too many requests.');
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Request failed with status ${response.status}`);
  }

  return response.json();
}
