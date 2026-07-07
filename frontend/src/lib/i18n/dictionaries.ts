/**
 * Translation dictionaries.
 *
 * English is the canonical shape: `Dictionary` is derived from `en.json`, and
 * the Arabic and Turkish catalogs are assigned through `asDictionary`, which
 * makes a missing key in any language a TYPE ERROR at build time. All
 * user-facing strings come from here — never hardcoded in components.
 */
import type { Locale } from "./config";
import ar from "./dictionaries/ar.json";
import en from "./dictionaries/en.json";
import tr from "./dictionaries/tr.json";

export type Dictionary = typeof en;

/** Compile-time completeness guard: the argument must match `Dictionary`. */
function asDictionary(dictionary: Dictionary): Dictionary {
  return dictionary;
}

const dictionaries: Record<Locale, Dictionary> = {
  ar: asDictionary(ar),
  en,
  tr: asDictionary(tr),
};

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}
