# LOCALE — Language auto-detection & manual override contract

**Status:** implemented 2026-10-08. Permanent rule: every platform auto-detects the
browser language on first visit, but the user can always switch; the manual
choice persists and wins on every future visit.

## Resolution order (frontend)

`frontend/client/src/lib/i18n.ts` — `resolveLocale({ stored, browser, defaultLocale })`:

1. **Saved choice** — `localStorage["locale"]` (also: the `locale` cookie). A valid
   saved value ALWAYS wins. An invalid value (`"pt"`, `""`, `null`) is ignored,
   never blocks.
2. **Browser language** — `navigator.language` mapped to the closest supported
   locale: exact match, then primary subtag (`"es-MX"` → `es`, `"en-US"` → `en`).
   Unsupported tags (`"pt-BR"`, `"ja"`) map to nothing.
3. **App default** — `es` (only reached for browsers with no supported language).

Supported locales: `es`, `en`. Default `es`: most of the existing UI chrome was
already Spanish, and it only affects visitors whose browser language is neither
es* nor en*.

## Application timing

- `main.tsx` calls `getInitialLocale()` at module scope, **before the first React
  render** — nothing ever flashes in the wrong language.
- `<html lang>` is set to the resolved locale on boot and on every manual change
  (screen readers / SEO).
- `LocaleProvider` (`contexts/LocaleContext.tsx`) exposes `locale`, `setLocale`,
  and `t(key, vars)` with `{name}` interpolation. Missing keys fail loudly in dev
  (`assertTranslationsComplete()`).

## Manual override — always visible

`components/LanguageToggle.tsx` — ES | EN segmented control rendered in:

- the sidebar footer + the mobile header of `DashboardLayout` (every authenticated page),
- the Login screen and onboarding form,
- the 404 page.

Changing it calls `persistLocale()`:

- `localStorage["locale"]` — read first on every visit,
- `locale` cookie — `Max-Age=31536000` (1 year), `Path=/`, `SameSite=Lax`.

## Backend contract

Every API request from `lib/api.ts` sends **`Accept-Language: <locale>`**
(resolved with the same saved > browser > default order). The backend
**currently ignores this header** — kept as the forward contract for any future
backend UI-string localization.

**N/A with evidence:** the backend does not serve UI strings. Localized *learning
content* (lesson text, stories, tutor replies, TTS) is generated per request from
**explicit request fields**, not from browser detection:

- `target_lang` / `native_lang` on content, lesson, practice, and conversation
  payloads (`backend/routers/content.py`, `lessons.py`, `conversation.py`),
- `content_lang` on academy enrollment (`routers/academy.py`),
- the learner's stored profile (`native_lang`, `target_lang`) as the source of
  those fields.

This is the correct separation: the UI locale (this document) is a display
preference; the content language is learning-domain data chosen explicitly per
learner. No backend change was needed, and none was made.

## Tests

`frontend/client/src/lib/i18n.test.ts` (vitest, `pnpm test`) — 16 cases covering:
saved > browser > default, invalid saved value ignored, `es-MX` → `es`,
`en-US` → `en`, unsupported browser language → default, custom default,
persistence round-trip (localStorage + 1-year cookie attributes), and
graceful behavior when storage/cookies are blocked.
