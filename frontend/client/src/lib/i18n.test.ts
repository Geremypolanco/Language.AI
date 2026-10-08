/**
 * Unit tests for the locale resolution order:
 *   saved choice > browser language > app default.
 * Run with: pnpm test  (vitest)
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  isSupportedLocale,
  matchBrowserLocale,
  resolveLocale,
  persistLocale,
  readStoredLocale,
  readCookieLocale,
  getEffectiveLocale,
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  LOCALE_COOKIE_NAME,
} from "./i18n";

describe("isSupportedLocale", () => {
  it("accepts es and en", () => {
    expect(isSupportedLocale("es")).toBe(true);
    expect(isSupportedLocale("en")).toBe(true);
  });

  it("rejects invalid saved values", () => {
    expect(isSupportedLocale("pt")).toBe(false);
    expect(isSupportedLocale("")).toBe(false);
    expect(isSupportedLocale(null)).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
    expect(isSupportedLocale(42)).toBe(false);
    expect(isSupportedLocale("ES")).toBe(false); // case-sensitive: must go through matchBrowserLocale
  });
});

describe("matchBrowserLocale", () => {
  it("maps es variants to es", () => {
    expect(matchBrowserLocale("es")).toBe("es");
    expect(matchBrowserLocale("es-MX")).toBe("es");
    expect(matchBrowserLocale("es_ES")).toBe("es");
  });

  it("maps en variants to en", () => {
    expect(matchBrowserLocale("en")).toBe("en");
    expect(matchBrowserLocale("en-US")).toBe("en");
  });

  it("returns null for unsupported languages", () => {
    expect(matchBrowserLocale("pt-BR")).toBe(null);
    expect(matchBrowserLocale("ja")).toBe(null);
    expect(matchBrowserLocale("fr")).toBe(null);
  });

  it("returns null for empty/missing input", () => {
    expect(matchBrowserLocale("")).toBe(null);
    expect(matchBrowserLocale(null)).toBe(null);
    expect(matchBrowserLocale(undefined)).toBe(null);
  });
});

describe("resolveLocale (saved > browser > default)", () => {
  it("a valid saved choice always wins", () => {
    expect(resolveLocale({ stored: "en", browser: "es-MX" })).toBe("en");
    expect(resolveLocale({ stored: "es", browser: "en-US" })).toBe("es");
  });

  it("falls back to the browser language when nothing is saved", () => {
    expect(resolveLocale({ browser: "es-MX" })).toBe("es");
    expect(resolveLocale({ browser: "en-US" })).toBe("en");
  });

  it("ignores an invalid saved value and uses the browser instead", () => {
    expect(resolveLocale({ stored: "pt", browser: "es" })).toBe("es");
    expect(resolveLocale({ stored: "", browser: "en" })).toBe("en");
    expect(resolveLocale({ stored: null, browser: "en" })).toBe("en");
  });

  it("falls back to the app default for unsupported browser languages", () => {
    expect(resolveLocale({ browser: "pt-BR" })).toBe(DEFAULT_LOCALE);
    expect(resolveLocale({ browser: "ja" })).toBe(DEFAULT_LOCALE);
    expect(resolveLocale({})).toBe(DEFAULT_LOCALE);
  });

  it("honors a custom default", () => {
    expect(resolveLocale({ browser: "pt-BR", defaultLocale: "en" })).toBe("en");
  });
});

describe("persistence (localStorage + 1-year cookie)", () => {
  const store = new Map<string, string>();
  let cookieJar = "";

  function stubNavigator(language: string) {
    Object.defineProperty(globalThis, "navigator", {
      value: { language },
      configurable: true,
    });
  }

  beforeEach(() => {
    store.clear();
    cookieJar = "";
    (globalThis as any).localStorage = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
    };
    (globalThis as any).document = {
      get cookie() {
        return cookieJar;
      },
      set cookie(v: string) {
        // keep only the name=value pair, like a real cookie jar
        const pair = v.split(";")[0];
        const name = pair.split("=")[0];
        const rest = cookieJar
          .split(";")
          .map((c) => c.trim())
          .filter(Boolean)
          .filter((c) => !c.startsWith(name + "="));
        rest.push(pair.trim());
        cookieJar = rest.join("; ");
      },
      documentElement: { setAttribute: () => {} },
    };
  });

  afterEach(() => {
    delete (globalThis as any).localStorage;
    delete (globalThis as any).document;
  });

  it("round-trips through localStorage and the cookie", () => {
    persistLocale("en");
    expect(readStoredLocale()).toBe("en");
    expect(readCookieLocale()).toBe("en");
    expect(store.get(LOCALE_STORAGE_KEY)).toBe("en");
  });

  it("the cookie carries a 1-year Max-Age and Path=/", () => {
    const seen: string[] = [];
    const doc = (globalThis as any).document;
    Object.defineProperty(doc, "cookie", {
      get: () => cookieJar,
      set: (v: string) => {
        seen.push(v);
        cookieJar = v.split(";")[0];
      },
      configurable: true,
    });
    persistLocale("es");
    expect(seen[0]).toContain(`${LOCALE_COOKIE_NAME}=es`);
    expect(seen[0]).toContain("Max-Age=31536000");
    expect(seen[0]).toContain("Path=/");
  });

  it("a persisted choice beats the browser on the next visit", () => {
    persistLocale("en");
    stubNavigator("es-MX");
    expect(getEffectiveLocale()).toBe("en");
  });

  it("an invalid persisted value is ignored in favor of the browser", () => {
    store.set(LOCALE_STORAGE_KEY, "pt");
    stubNavigator("es");
    expect(getEffectiveLocale()).toBe("es");
  });

  it("works when storage/cookies are unavailable (private mode)", () => {
    delete (globalThis as any).localStorage;
    delete (globalThis as any).document;
    expect(() => persistLocale("es")).not.toThrow();
    expect(readStoredLocale()).toBe(null);
    expect(readCookieLocale()).toBe(null);
  });
});
