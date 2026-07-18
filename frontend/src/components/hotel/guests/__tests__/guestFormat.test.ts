import { describe, expect, it } from "vitest";

import {
  formatDateOnly,
  formatIdentifier,
  formatQuantity,
  isMaskedValue,
  maskGuard,
} from "../guestFormat";

describe("guestFormat.formatQuantity", () => {
  it("renders quantities with the locale numerals", () => {
    expect(formatQuantity(3, "en")).toBe("3");
  });

  it("falls back to zero for missing input", () => {
    expect(formatQuantity(null, "en")).toBe("0");
    expect(formatQuantity(undefined, "en")).toBe("0");
  });
});

describe("guestFormat.formatIdentifier", () => {
  it("keeps identifier digits verbatim (never localised)", () => {
    expect(formatIdentifier("0555123456")).toBe("0555123456");
    expect(formatIdentifier("A1234567")).toBe("A1234567");
  });

  it("renders an em dash for empty identifiers", () => {
    expect(formatIdentifier("")).toBe("—");
    expect(formatIdentifier(null)).toBe("—");
    expect(formatIdentifier(undefined)).toBe("—");
  });
});

describe("guestFormat.formatDateOnly", () => {
  it("shows the exact calendar day with no UTC shift", () => {
    const out = formatDateOnly("2026-07-15", "en");
    expect(out).toContain("15");
    expect(out).toContain("2026");
  });

  it("returns an em dash for missing values and passes through non-dates", () => {
    expect(formatDateOnly(null, "en")).toBe("—");
    expect(formatDateOnly("not-a-date", "en")).toBe("not-a-date");
  });
});

describe("guestFormat mask guard", () => {
  it("detects masked values", () => {
    expect(isMaskedValue("••••")).toBe(true);
    expect(isMaskedValue("1234")).toBe(false);
    expect(isMaskedValue(null)).toBe(false);
  });

  it("omits a masked value so it is never re-sent", () => {
    expect(maskGuard("••••")).toBeUndefined();
    expect(maskGuard("1234")).toBe("1234");
    expect(maskGuard(null)).toBeUndefined();
  });
});
