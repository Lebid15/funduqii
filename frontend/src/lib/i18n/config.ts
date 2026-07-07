/**
 * Central i18n configuration for the Funduqii frontend.
 *
 * The platform supports Arabic, English and Turkish. Arabic is RTL; English
 * and Turkish are LTR. Locale routing is introduced in a later phase — Phase 1
 * only establishes the extensible scaffold.
 */
export const locales = ["ar", "en", "tr"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

const rtlLocales: readonly Locale[] = ["ar"];

export function isRtl(locale: Locale): boolean {
  return rtlLocales.includes(locale);
}

export function dir(locale: Locale): "rtl" | "ltr" {
  return isRtl(locale) ? "rtl" : "ltr";
}
