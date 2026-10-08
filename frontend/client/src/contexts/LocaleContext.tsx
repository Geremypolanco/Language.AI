import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import {
  applyLocaleToDocument,
  getInitialLocale,
  persistLocale,
  SUPPORTED_LOCALES,
  type Locale,
} from "@/lib/i18n";
import { TRANSLATIONS, assertTranslationsComplete } from "@/lib/translations";

interface LocaleContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** t("path.title") → translated string; t("login.onboarding.subtitle", { name }) interpolates {name}. */
  t: (key: string, vars?: Record<string, string | number>) => string;
  supportedLocales: readonly Locale[];
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

// Fail fast in dev if a dictionary is missing keys — a half-translated UI
// is worse than a build error.
if (import.meta.env.DEV) {
  const missing = assertTranslationsComplete();
  if (missing.length > 0) {
    console.error("[i18n] missing translation keys:", missing);
  }
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // Initializer runs before the first render — combined with main.tsx's
  // module-scope getInitialLocale(), nothing ever paints in the wrong language.
  const [locale, setLocaleState] = useState<Locale>(() => getInitialLocale());

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    persistLocale(next); // localStorage + 1-year cookie
    applyLocaleToDocument(next); // <html lang>
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      let text = TRANSLATIONS[locale][key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          text = text.replaceAll(`{${k}}`, String(v));
        }
      }
      return text;
    },
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t, supportedLocales: SUPPORTED_LOCALES }),
    [locale, setLocale, t]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextType {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}
