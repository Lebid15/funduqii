"use client";

import { locales, type Locale } from "@/lib/i18n/config";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Switches the active locale (persists it + flips RTL/LTR instantly). */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return (
    <label className="cluster">
      <span className="sr-only">{t.language.label}</span>
      <select
        className="select"
        style={{ width: "auto" }}
        value={locale}
        aria-label={t.language.label}
        onChange={(event) => setLocale(event.target.value as Locale)}
      >
        {locales.map((code) => (
          <option key={code} value={code}>
            {t.language[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
