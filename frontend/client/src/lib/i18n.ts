/**
 * Locale detection, resolution, and persistence.
 *
 * Resolution order (permanent rule, 2026-10-08):
 *   1. Manual choice — `localStorage["locale"]` (and the `locale` cookie),
 *      persisted when the user flips the visible language toggle. A valid
 *      saved value ALWAYS wins.
 *   2. Browser language — `navigator.language`, mapped to the closest
 *      supported locale (e.g. "es-MX" → "es", "en-US" → "en").
 *   3. App default ("es") — only for browsers whose language matches no
 *      supported locale.
 *
 * The pure functions (resolveLocale / matchBrowserLocale / isSupportedLocale)
 * are dependency-free so they can be unit-tested without a DOM.
 */

export const SUPPORTED_LOCALES = ["es", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

/** App default — used only when the browser language maps to nothing supported. */
export const DEFAULT_LOCALE: Locale = "es";

export const LOCALE_STORAGE_KEY = "locale";
export const LOCALE_COOKIE_NAME = "locale";
/** 1 year, in seconds. */
export const LOCALE_COOKIE_MAX_AGE = 31536000;

/** Type guard: only "es"/"en" strings pass — everything else (null, "", "pt", 42) is rejected. */
export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Maps a BCP-47 browser language tag to the closest supported locale.
 * - Exact match wins ("es" → "es", "en" → "en").
 * - Otherwise the primary language subtag is matched ("es-MX" → "es", "en-US" → "en").
 * - Returns null when nothing matches ("pt-BR", "ja", "") so the caller falls
 *   back to the app default instead of guessing.
 */
export function matchBrowserLocale(browserLanguage: string | null | undefined): Locale | null {
  if (!browserLanguage || typeof browserLanguage !== "string") return null;
  const tag = browserLanguage.trim().toLowerCase();
  if (!tag) return null;
  if (isSupportedLocale(tag)) return tag;
  const primary = tag.split(/[-_]/)[0];
  if (isSupportedLocale(primary)) return primary;
  return null;
}

export interface ResolveLocaleInput {
  /** Value previously persisted via persistLocale (localStorage). Invalid values are ignored. */
  stored?: unknown;
  /** navigator.language at first visit. */
  browser?: string | null;
  /** App default; DEFAULT_LOCALE unless overridden. */
  defaultLocale?: Locale;
}

/**
 * Pure resolution: saved choice > browser language > default.
 * An invalid saved value never blocks — it is simply skipped.
 */
export function resolveLocale({
  stored,
  browser,
  defaultLocale = DEFAULT_LOCALE,
}: ResolveLocaleInput = {}): Locale {
  if (isSupportedLocale(stored)) return stored;
  return matchBrowserLocale(browser) ?? defaultLocale;
}

// ── Browser persistence (guarded: safe to import in non-DOM environments) ──

function hasDOM(): boolean {
  return typeof document !== "undefined" && typeof window !== "undefined";
}

/** Reads the persisted manual choice from localStorage; null when absent/unreadable. */
export function readStoredLocale(): string | null {
  try {
    if (typeof localStorage === "undefined") return null;
    return localStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Reads the `locale` cookie; used as a secondary signal (also sent to the backend). */
export function readCookieLocale(): string | null {
  try {
    if (typeof document === "undefined") return null;
    const match = document.cookie
      .split(";")
      .map((c) => c.trim().split("="))
      .find(([k]) => k === LOCALE_COOKIE_NAME);
    return match?.[1] ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

/**
 * Persists the user's manual choice in BOTH places:
 * - localStorage["locale"] — read first on every visit (survives cookie clears).
 * - `locale` cookie (1 year, Path=/, SameSite=Lax) — readable by the backend
 *   and sent automatically with API requests.
 */
export function persistLocale(locale: Locale): void {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    }
  } catch {
    // Storage full/blocked — the cookie below still carries the choice.
  }
  try {
    if (typeof document !== "undefined") {
      document.cookie =
        `${LOCALE_COOKIE_NAME}=${encodeURIComponent(locale)}; ` +
        `Max-Age=${LOCALE_COOKIE_MAX_AGE}; Path=/; SameSite=Lax`;
    }
  } catch {
    // Cookie blocked — localStorage above still carries the choice.
  }
}

/** Keeps <html lang> in sync — screen readers and SEO read it, not our context. */
export function applyLocaleToDocument(locale: Locale): void {
  if (!hasDOM()) return;
  document.documentElement.setAttribute("lang", locale);
}

/**
 * The value to boot the app with — call BEFORE the first React render
 * (main.tsx does this at module scope) so nothing ever flashes in the
 * wrong language. Also applies <html lang> immediately.
 */
export function getInitialLocale(): Locale {
  const stored = readStoredLocale() ?? readCookieLocale();
  const browser = typeof navigator !== "undefined" ? navigator.language : null;
  const locale = resolveLocale({ stored, browser });
  applyLocaleToDocument(locale);
  return locale;
}

/**
 * Current effective locale for non-React call sites (e.g. the API client).
 * Reads the persisted choice first, then the browser — same order as resolveLocale.
 */
export function getEffectiveLocale(): Locale {
  const stored = readStoredLocale() ?? readCookieLocale();
  const browser = typeof navigator !== "undefined" ? navigator.language : null;
  return resolveLocale({ stored, browser });
}
