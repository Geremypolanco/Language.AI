import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiFetch } from '../utils/api.js';
import {
  loadAnalyticsScripts,
  unloadAnalyticsScripts,
  loadMarketingScripts,
  unloadMarketingScripts,
} from '../utils/thirdPartyScripts.js';

const ConsentContext = createContext(null);

const DEFAULT_PREFERENCES = { essential: true, analytics: false, marketing: false };

/**
 * Single source of truth for cookie consent. The banner, the settings modal,
 * and any script-loading logic all read/write through here so there is one
 * place that decides whether analytics/marketing scripts are allowed to run.
 *
 * Preferences live server-side in an HttpOnly cookie (see server/utils/cookies.js),
 * so on mount we ask the server what was previously chosen instead of reading
 * document.cookie directly.
 */
export function ConsentProvider({ children }) {
  const [preferences, setPreferences] = useState(DEFAULT_PREFERENCES);
  const [hasConsented, setHasConsented] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch('/consent')
      .then((data) => {
        setHasConsented(data.hasConsented);
        setPreferences(data.preferences);
        if (data.hasConsented) applyScriptGating(data.preferences);
      })
      .catch(() => {
        // If the consent check fails, fail closed: keep the banner visible
        // and no non-essential scripts loaded.
        setHasConsented(false);
      })
      .finally(() => setLoading(false));
  }, []);

  function applyScriptGating(prefs) {
    if (prefs.analytics) loadAnalyticsScripts();
    else unloadAnalyticsScripts();

    if (prefs.marketing) loadMarketingScripts();
    else unloadMarketingScripts();
  }

  const savePreferences = useCallback(async (nextPrefs) => {
    const merged = { ...DEFAULT_PREFERENCES, ...nextPrefs };
    const data = await apiFetch('/consent', {
      method: 'POST',
      body: JSON.stringify(merged),
    });
    setPreferences(data.preferences);
    setHasConsented(true);
    applyScriptGating(data.preferences);
  }, []);

  const acceptAll = useCallback(() => savePreferences({ analytics: true, marketing: true }), [savePreferences]);
  const rejectNonEssential = useCallback(() => savePreferences({ analytics: false, marketing: false }), [savePreferences]);

  return (
    <ConsentContext.Provider
      value={{ preferences, hasConsented, loading, savePreferences, acceptAll, rejectNonEssential }}
    >
      {children}
    </ConsentContext.Provider>
  );
}

export function useConsent() {
  const ctx = useContext(ConsentContext);
  if (!ctx) throw new Error('useConsent must be used within a ConsentProvider');
  return ctx;
}
