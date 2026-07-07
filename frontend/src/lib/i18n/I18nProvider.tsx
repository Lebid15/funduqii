"use client";

/**
 * Client-side i18n context.
 *
 * Holds the active locale, exposes the matching dictionary and a `setLocale`
 * that persists the choice (cookie) and updates `<html lang dir>` so RTL/LTR
 * flips instantly. Every client component reads text via `useI18n().t`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { LOCALE_COOKIE, dir, type Locale } from "./config";
import { getDictionary, type Dictionary } from "./dictionaries";

interface I18nValue {
  locale: Locale;
  dir: "rtl" | "ltr";
  t: Dictionary;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export function I18nProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${ONE_YEAR_SECONDS}; samesite=lax`;
    const root = document.documentElement;
    root.lang = next;
    root.dir = dir(next);
  }, []);

  const value = useMemo<I18nValue>(
    () => ({
      locale,
      dir: dir(locale),
      t: getDictionary(locale),
      setLocale,
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n must be used within an I18nProvider.");
  }
  return value;
}
