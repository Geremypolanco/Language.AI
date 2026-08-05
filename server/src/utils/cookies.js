import { env } from '../config/env.js';

export const CONSENT_COOKIE_NAME = 'consent_prefs';

/**
 * Cookie options shared by every cookie this app sets.
 * HttpOnly + Secure + SameSite=Strict per GDPR/CCPA guidance: preferences are
 * unreadable to client-side JS (mitigates XSS exfiltration) and are never sent
 * cross-site.
 */
export function secureCookieOptions(maxAgeMs) {
  return {
    httpOnly: true,
    secure: env.isProduction, // requires HTTPS in production; relaxed only for local http dev
    sameSite: 'strict',
    domain: env.cookieDomain,
    path: '/',
    maxAge: maxAgeMs,
  };
}

const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;

/**
 * Consent preferences stored server-side as an HttpOnly cookie so they can't
 * be tampered with via document.cookie, while still being readable by the
 * server on every request to decide what to render/serve.
 */
export function setConsentCookie(res, preferences) {
  res.cookie(CONSENT_COOKIE_NAME, JSON.stringify(preferences), secureCookieOptions(ONE_YEAR_MS));
}

export function clearConsentCookie(res) {
  res.clearCookie(CONSENT_COOKIE_NAME, secureCookieOptions(0));
}

export function readConsentCookie(req) {
  const raw = req.cookies?.[CONSENT_COOKIE_NAME];
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return {
      essential: true, // always true, cannot be disabled
      analytics: Boolean(parsed.analytics),
      marketing: Boolean(parsed.marketing),
    };
  } catch {
    return null;
  }
}
