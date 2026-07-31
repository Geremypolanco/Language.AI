import { filterXSS } from 'xss';

const xssOptions = {
  whiteList: {}, // strip all HTML tags — chat input is plain text, never markup
  stripIgnoreTag: true,
  stripIgnoreTagBody: ['script', 'style'],
};

function sanitizeValue(value) {
  if (typeof value === 'string') {
    return filterXSS(value, xssOptions).trim();
  }
  if (Array.isArray(value)) {
    return value.map(sanitizeValue);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, sanitizeValue(v)]));
  }
  return value;
}

/**
 * Recursively strips HTML/script payloads from every string in the request
 * body before it reaches route handlers or is forwarded to the AI provider.
 * This is defense-in-depth against XSS: it does not replace output-side
 * escaping on the client, it prevents a malicious payload from ever being
 * persisted, echoed, or relayed upstream in the first place.
 */
export function sanitizeBody(req, _res, next) {
  if (req.body && typeof req.body === 'object') {
    req.body = sanitizeValue(req.body);
  }
  next();
}
