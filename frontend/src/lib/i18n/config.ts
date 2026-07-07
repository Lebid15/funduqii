/**
 * Central i18n configuration for the Funduqii frontend.
 *
 * The platform supports Arabic, English and Turkish. Arabic is RTL; English
 * and Turkish are LTR. The active locale is persisted in a cookie so the server
 * layout can set `<html dir lang>` on the first paint (no flash), and the
 * client `I18nProvider` can switch it at runtime.
 */
export const locales = ["ar", "en", "tr"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

/** Cookie that stores the user's chosen locale (readable on server & client). */
export const LOCALE_COOKIE = "funduqii_locale";

const rtlLocales: readonly Locale[] = ["ar"];

export function isRtl(locale: Locale): boolean {
  return rtlLocales.includes(locale);
}

export function dir(locale: Locale): "rtl" | "ltr" {
  return isRtl(locale) ? "rtl" : "ltr";
}

/** Narrow an arbitrary string to a supported locale, falling back to default. */
export function resolveLocale(value: string | undefined | null): Locale {
  return locales.includes(value as Locale) ? (value as Locale) : defaultLocale;
}
