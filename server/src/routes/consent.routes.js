import { Router } from 'express';
import { consentPreferencesSchema } from '../schemas/consentSchema.js';
import { setConsentCookie, clearConsentCookie, readConsentCookie } from '../utils/cookies.js';

export const consentRouter = Router();

// Read current consent state (used by the client on load to sync UI without
// ever touching document.cookie, since the cookie is HttpOnly).
consentRouter.get('/', (req, res) => {
  const prefs = readConsentCookie(req);
  res.json({
    hasConsented: prefs !== null,
    preferences: prefs ?? { essential: true, analytics: false, marketing: false },
  });
});

// Persist the user's consent choice as a secure, HttpOnly cookie.
consentRouter.post('/', (req, res) => {
  const parsed = consentPreferencesSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'invalid_preferences', details: parsed.error.flatten() });
  }
  const preferences = { essential: true, ...parsed.data };
  setConsentCookie(res, preferences);
  res.json({ ok: true, preferences });
});

consentRouter.delete('/', (req, res) => {
  clearConsentCookie(res);
  res.json({ ok: true });
});
