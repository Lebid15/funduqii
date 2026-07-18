/**
 * Guests-local presentation helpers (GUESTS-CLOSURE foundation).
 *
 * SCOPE: guests section only — this never replaces the shared `@/lib/format`
 * helpers. It encodes the guest-identity display rules the closure programme
 * requires:
 *
 *  - QUANTITIES (stays_count / nights / document counts) render with the active
 *    locale's own numerals, exactly like `formatMoney`/`formatCapacity`.
 *  - IDENTIFIERS (phone / national_id / document number) NEVER have their digits
 *    localised: they stay Latin and must be rendered LTR (wrap in
 *    `<bdi dir="ltr">…</bdi>` — see `IDENTIFIER_DIR`) so an Arabic/RTL layout can
 *    never reorder or transliterate an identifier's digits.
 *  - Date-only values render WITHOUT a UTC shift: a `YYYY-MM-DD` string is shown
 *    as that exact calendar day regardless of the viewer's timezone (the shared
 *    `formatDate` builds a `Date` from the ISO string and can slip a day).
 *  - A MASK GUARD (`isMaskedValue`) lets forms detect a server-masked value
 *    (bullet characters) so a masked identifier is never echoed back on save.
 */
import type { Locale } from "@/lib/i18n/config";

/** The bullet character the backend uses to mask sensitive values. */
export const MASK_CHAR = "•"; // •

/** Identifiers must render left-to-right regardless of the page direction. */
export const IDENTIFIER_DIR = "ltr" as const;

const EM_DASH = "—"; // —

/**
 * True when a value has been masked server-side (contains bullet characters).
 * A masked value is display-only and must NEVER be sent back on a write — the
 * form should omit the field so the stored value is preserved.
 */
export function isMaskedValue(value: string | null | undefined): boolean {
  return typeof value === "string" && value.includes(MASK_CHAR);
}

/**
 * Guard a value before re-sending it: returns `undefined` (i.e. "omit this
 * field") when the value is masked, otherwise the value unchanged.
 */
export function maskGuard(value: string | null | undefined): string | undefined {
  if (value === null || value === undefined) return undefined;
  return isMaskedValue(value) ? undefined : value;
}

/**
 * Format a QUANTITY (stays_count, nights, counts) with the locale's numerals.
 * Non-finite input falls back to `0` so a card never prints `NaN`.
 */
export function formatQuantity(
  value: number | null | undefined,
  locale: Locale,
): string {
  const n = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return new Intl.NumberFormat(locale).format(n);
}

/**
 * Render an IDENTIFIER (phone / national_id / document number) verbatim — the
 * digits are NEVER localised. Empty/missing renders an em dash. The caller MUST
 * still wrap the result in `<bdi dir={IDENTIFIER_DIR}>` so RTL layouts keep the
 * digits in order.
 */
export function formatIdentifier(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  return text === "" ? EM_DASH : text;
}

/**
 * Render a DATE-ONLY value (`YYYY-MM-DD`) as that exact calendar day, with NO
 * timezone/UTC shift. Builds the date from its calendar parts in local time so
 * the displayed day always equals the stored day. Full ISO datetimes are not the
 * concern here (use the shared `formatDateTime`); anything unparseable is
 * returned unchanged, and empty renders an em dash.
 */
export function formatDateOnly(
  value: string | null | undefined,
  locale: Locale,
): string {
  if (!value) return EM_DASH;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}
