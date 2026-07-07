/**
 * Translation dictionaries.
 *
 * All user-facing strings come from these central catalogs — never hardcoded
 * in components. The shape is shared across every locale via the `Dictionary`
 * interface, so a missing key in any language is a type error.
 */
import type { Locale } from "./config";
import ar from "./dictionaries/ar.json";
import en from "./dictionaries/en.json";
import tr from "./dictionaries/tr.json";

export interface Dictionary {
  app: {
    name: string;
    foundationReady: string;
    phase: string;
  };
  common: {
    loading: string;
    error: string;
  };
}

const dictionaries: Record<Locale, Dictionary> = {
  ar: ar as Dictionary,
  en: en as Dictionary,
  tr: tr as Dictionary,
};

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}
