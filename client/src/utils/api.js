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
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (response.status === 429) {
    const body = await response.json().catch(() => ({}));
    const retryAfterHeader = Number(response.headers.get('Retry-After'));
    const retryAfterSeconds = body.retryAfterSeconds ?? (Number.isFinite(retryAfterHeader) ? retryAfterHeader : 60);
    throw new RateLimitError(retryAfterSeconds, body.message || 'Too many requests.');
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Request failed with status ${response.status}`);
  }

  return response.json();
}
