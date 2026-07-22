"use client";

import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import type { PaymentMethod } from "@/lib/api/types";

/**
 * Cosmetic permission gate — every API re-checks server-side regardless.
 *
 * Two DIFFERENT cases, deliberately (mirrors the guest-folio `useCan`):
 * - `access === null` (outside the hotel shell, e.g. the platform console) reads
 *   as "allowed" — there is no hotel membership to check against.
 * - Still LOADING reads as "denied" (fail-closed): `!access.loading && ...`. A
 *   control appears only once the permission check has RESOLVED, so an action
 *   never flashes into view then vanishes — or, worse, is clicked and eats a 403.
 */
export function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/**
 * Payment methods for an expense, in the owner's preferred order: cash +
 * electronic are surfaced FIRST (the two the owner wants emphasised), the rest
 * follow. The full backend `PaymentMethod` set is still offered — never widened
 * or narrowed here (the server validates against its own choices). Labels are
 * reused from the finance dictionary (`t.finance.methods`).
 */
export const EXPENSE_METHODS: readonly PaymentMethod[] = [
  "cash",
  "electronic",
  "card",
  "bank_transfer",
  "other",
];

/** Accepted receipt attachment types (image + PDF). Kept in sync with the
 * backend's private-media validation; the server stays authoritative. */
export const RECEIPT_ACCEPT = "image/*,application/pdf";
