import { useState } from 'react';
import { useConsent } from '../context/ConsentContext.jsx';
import './CookieConsentBanner.css';

export default function CookieConsentBanner() {
  const { hasConsented, loading, acceptAll, rejectNonEssential, savePreferences, preferences } = useConsent();
  const [showCustomize, setShowCustomize] = useState(false);
  const [draft, setDraft] = useState({ analytics: preferences.analytics, marketing: preferences.marketing });

  if (loading || hasConsented) return null;

  return (
    <div className="cookie-banner" role="dialog" aria-live="polite" aria-label="Preferencias de cookies">
      <div className="cookie-banner__content">
        <p className="cookie-banner__text">
          Usamos cookies esenciales para el funcionamiento del sitio. Con tu permiso, también usamos cookies
          analíticas y de marketing para mejorar tu experiencia. Ninguna cookie no esencial se activa hasta que
          eliges "Aceptar todo". Consulta nuestra política de privacidad para más detalles.
        </p>

        {showCustomize && (
          <fieldset className="cookie-banner__options">
            <label className="cookie-banner__option">
              <input type="checkbox" checked disabled />
              Esenciales (siempre activas)
            </label>
            <label className="cookie-banner__option">
              <input
                type="checkbox"
                checked={draft.analytics}
                onChange={(e) => setDraft((d) => ({ ...d, analytics: e.target.checked }))}
              />
              Analíticas
            </label>
            <label className="cookie-banner__option">
              <input
                type="checkbox"
                checked={draft.marketing}
                onChange={(e) => setDraft((d) => ({ ...d, marketing: e.target.checked }))}
              />
              Marketing
            </label>
          </fieldset>
        )}

        <div className="cookie-banner__actions">
          {!showCustomize && (
            <button type="button" className="cookie-banner__btn cookie-banner__btn--ghost" onClick={() => setShowCustomize(true)}>
              Personalizar
            </button>
          )}
          <button type="button" className="cookie-banner__btn cookie-banner__btn--secondary" onClick={rejectNonEssential}>
            Rechazar no esenciales
          </button>
          {showCustomize ? (
            <button type="button" className="cookie-banner__btn cookie-banner__btn--primary" onClick={() => savePreferences(draft)}>
              Guardar preferencias
            </button>
          ) : (
            <button type="button" className="cookie-banner__btn cookie-banner__btn--primary" onClick={acceptAll}>
              Aceptar todo
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
