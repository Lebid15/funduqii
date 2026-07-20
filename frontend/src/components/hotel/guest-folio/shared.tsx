"use client";

import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import type {
  GuestServiceCategory,
  GuestServicePricingMode,
} from "@/lib/api/types";

/**
 * Cosmetic permission gate — every API re-checks server-side regardless.
 *
 * Two DIFFERENT cases, deliberately:
 * - `access === null` (outside the hotel shell, e.g. the platform console) reads
 *   as "allowed" — there is no hotel membership to check against.
 * - Still LOADING reads as "denied" (fail-closed): `!access.loading && ...`. A
 *   control therefore appears only once the permission check has RESOLVED, so a
 *   user never sees an action flash into view and then vanish — or, worse, clicks
 *   one they do not hold and eats a 403.
 *
 * Money is gated separately by `useCanSeeMoney` below, which resolves the single
 * code `finance.view` rather than an any-of set.
 */
export function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/**
 * Resolved finance-visibility gate for MONEY. Unlike `useCan`, this is strict:
 * it is only true once the access context has RESOLVED and actually grants
 * `finance.view` (`null`/platform console = shows everything). This prevents a
 * total/balance flashing before the permission check settles.
 */
export function useCanSeeMoney(): boolean {
  const access = useHotelAccess();
  if (access === null) return true;
  return !access.loading && access.can("finance.view");
}

/** The nine catalog categories (backend GuestServiceCategory). */
export const GUEST_SERVICE_CATEGORIES: readonly GuestServiceCategory[] = [
  "laundry",
  "parking",
  "transport",
  "minibar",
  "extra_bed",
  "special_cleaning",
  "damages",
  "external_request",
  "other",
];

/** The two pricing modes (backend PricingMode). */
export const GUEST_SERVICE_PRICING_MODES: readonly GuestServicePricingMode[] = [
  "fixed",
  "variable",
];
