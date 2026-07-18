import { describe, expect, it } from "vitest";

import { getDictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/config";

import { messageForError } from "../errors";
import type { ApiError } from "../client";

/**
 * errors.messageForError (MANDATE W7, list item 5). The three GUESTS-CLOSURE
 * codes must map to their translated strings across every locale.
 */

function err(code: string, status = 400): ApiError {
  return { status, code, message: code };
}

const locales: Locale[] = ["ar", "en", "tr"];

describe("messageForError — guest identity codes", () => {
  it.each(locales)("maps guest_identity_conflict (%s)", (locale) => {
    const t = getDictionary(locale);
    expect(messageForError(err("guest_identity_conflict", 409), t)).toBe(
      t.guests.errors.identityConflict,
    );
  });

  it.each(locales)("maps invalid_phone (%s)", (locale) => {
    const t = getDictionary(locale);
    expect(messageForError(err("invalid_phone"), t)).toBe(
      t.guests.errors.invalidPhone,
    );
  });

  it.each(locales)("maps guest_blocked (%s)", (locale) => {
    const t = getDictionary(locale);
    expect(messageForError(err("guest_blocked", 409), t)).toBe(
      t.guests.errors.blocked,
    );
  });

  it("does not fall back to the generic message for these codes (en)", () => {
    const t = getDictionary("en");
    for (const code of ["guest_identity_conflict", "invalid_phone", "guest_blocked"]) {
      expect(messageForError(err(code), t)).not.toBe(t.errors.generic);
    }
  });
});
