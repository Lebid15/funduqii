import { describe, expect, it } from "vitest";

import ar from "../dictionaries/ar.json";
import en from "../dictionaries/en.json";
import tr from "../dictionaries/tr.json";

/**
 * [MANDATE W7, Decision 14] AUTOMATED, GATE-BLOCKING i18n parity.
 *
 * The three locale dictionaries (ar / en / tr) MUST expose the IDENTICAL set of
 * leaf key-paths — no key missing in any language and no extra/unused-only key.
 * This test is collected by `npm run test:run`, so it FAILS the suite the moment
 * the dictionaries diverge (a missing translation, an accidental extra key, or a
 * shape mismatch). It replaces the previous manual review convention.
 */

type Json = Record<string, unknown>;

/** All leaf key-paths of a nested dictionary (arrays are treated as leaves). */
function leafPaths(obj: Json, prefix = ""): string[] {
  const out: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      out.push(...leafPaths(value as Json, path));
    } else {
      out.push(path);
    }
  }
  return out;
}

const paths = {
  ar: new Set(leafPaths(ar as Json)),
  en: new Set(leafPaths(en as Json)),
  tr: new Set(leafPaths(tr as Json)),
};

/** Keys in `a` that are absent from `b`. */
function missingFrom(a: Set<string>, b: Set<string>): string[] {
  return [...a].filter((key) => !b.has(key)).sort();
}

describe("i18n dictionary parity (ar / en / tr)", () => {
  it("loads three non-trivial dictionaries", () => {
    expect(paths.en.size).toBeGreaterThan(1000);
    expect(paths.ar.size).toBe(paths.en.size);
    expect(paths.tr.size).toBe(paths.en.size);
  });

  it("has NO key missing from any locale and NO extra/unused-only key", () => {
    const diffs = {
      "in en, missing from ar": missingFrom(paths.en, paths.ar),
      "in en, missing from tr": missingFrom(paths.en, paths.tr),
      "in ar, missing from en": missingFrom(paths.ar, paths.en),
      "in tr, missing from en": missingFrom(paths.tr, paths.en),
      "in ar, missing from tr": missingFrom(paths.ar, paths.tr),
      "in tr, missing from ar": missingFrom(paths.tr, paths.ar),
    };
    const offenders = Object.fromEntries(
      Object.entries(diffs).filter(([, list]) => list.length > 0),
    );
    // An empty object means perfect parity; anything else prints the exact
    // divergent key-paths so a reviewer can fix them immediately.
    expect(offenders).toEqual({});
  });
});
