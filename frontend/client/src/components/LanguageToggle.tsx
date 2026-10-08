import { useLocale } from "@/contexts/LocaleContext";
import { SUPPORTED_LOCALES, type Locale } from "@/lib/i18n";

/**
 * Always-visible language toggle — ES | EN segmented control.
 * Manual choice persists (localStorage + 1-year cookie) and overrides
 * browser detection on every future visit.
 */
export default function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t } = useLocale();

  return (
    <div
      role="group"
      aria-label={t("common.toggleLanguage")}
      className={`inline-flex items-center rounded-full border border-border bg-muted/50 p-0.5 ${
        compact ? "text-xs" : "text-sm"
      }`}
    >
      {SUPPORTED_LOCALES.map((l: Locale) => {
        const active = l === locale;
        return (
          <button
            key={l}
            type="button"
            onClick={() => setLocale(l)}
            aria-pressed={active}
            title={t("common.toggleLanguage")}
            className={`rounded-full font-semibold uppercase transition-smooth ${
              compact ? "px-2.5 py-1" : "px-3 py-1.5"
            } ${
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}
