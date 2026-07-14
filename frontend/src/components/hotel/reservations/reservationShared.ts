import {
  Building2,
  CalendarClock,
  CalendarX2,
  Footprints,
  Globe,
  Phone,
  Sparkle,
  Sunrise,
  type LucideIcon,
} from "lucide-react";

import type { BadgeTone } from "@/components/ui";
import type {
  OccupantRelationship,
  Payment,
  ReservationDocumentType,
  ReservationOccupant,
  ReservationPaymentStatus,
} from "@/lib/api/types";
import type { ReservationSource } from "@/lib/api/types";
import type { Dictionary } from "@/lib/i18n/dictionaries";

/** SOURCE badge (direct / phone / walk_in / public_website / other) — tone +
 * icon, never colour alone (WCAG). The public website is the only highlighted
 * source; everything else is neutral. */
export function sourceTone(source: ReservationSource): BadgeTone {
  return source === "public_website" ? "info" : "neutral";
}

/** PAYMENT-STATUS badge tone for the card's financial summary (§35): paid →
 * success, partially paid → warning, unpaid → neutral (an unpaid FUTURE booking
 * is normal, never an error). Colour is always paired with a text label. */
export function paymentStatusTone(status: ReservationPaymentStatus): BadgeTone {
  switch (status) {
    case "paid":
      return "success";
    case "partial":
      return "warning";
    default:
      return "neutral"; // unpaid
  }
}

export function sourceIcon(source: ReservationSource): LucideIcon {
  switch (source) {
    case "public_website":
      return Globe;
    case "phone":
      return Phone;
    case "walk_in":
      return Footprints;
    case "direct":
      return Building2;
    default:
      return Sparkle; // other
  }
}

export type ArrivalFlagKind = "today" | "tomorrow" | "late";

export interface ArrivalFlag {
  kind: ArrivalFlagKind;
  label: string;
  icon: LucideIcon;
  tone: BadgeTone;
}

/** Parse a plain "YYYY-MM-DD" as a timezone-stable UTC day number. */
function dayNumber(iso: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return null;
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) / 86_400_000;
}

/**
 * Client-side arrival flag derived from the reservation's check-in date vs the
 * hotel business date (from the overview). Only meaningful for a still-active
 * booking that has NOT yet been checked in — cancelled/expired or in-house
 * reservations return null so the chip never misleads.
 */
export function arrivalFlag(
  checkInDate: string,
  businessDate: string | null,
  status: string,
  hasInHouseStay: boolean,
  t: Dictionary,
): ArrivalFlag | null {
  if (!businessDate) return null;
  if (hasInHouseStay) return null;
  if (status !== "held" && status !== "confirmed") return null;
  const ci = dayNumber(checkInDate);
  const bd = dayNumber(businessDate);
  if (ci === null || bd === null) return null;
  const diff = ci - bd;
  const c = t.reservations.card;
  if (diff < 0) {
    return { kind: "late", label: c.arrivalOverdue, icon: CalendarX2, tone: "warning" };
  }
  if (diff === 0) {
    return { kind: "today", label: c.arrivesToday, icon: Sunrise, tone: "info" };
  }
  if (diff === 1) {
    return { kind: "tomorrow", label: c.arrivesTomorrow, icon: CalendarClock, tone: "neutral" };
  }
  return null;
}

/* -------------------------------------------------------------------------- */
/* Structured-snapshot display helpers (RESERVATIONS-FORM-REWORK, Wave 3)     */
/* -------------------------------------------------------------------------- */

/** Sensitive ids come back masked from the server as bullet characters (the
 * guests-panel convention). Mirrored here so the read UI can style/label a
 * masked value without importing the wizard. */
export function isMaskedValue(value: string | null | undefined): boolean {
  return Boolean(value && value.includes("•"));
}

/** Localized label for an adult companion's relationship. The read DTO widens
 * the enum with "" (a stored occupant may carry no relationship) — that falls
 * back to the neutral "Other" label so a row never renders a raw code. */
export function relationshipLabel(
  value: OccupantRelationship | "",
  t: Dictionary,
): string {
  const labels = t.reservations.wizard.relationship;
  if (value && value in labels) {
    return labels[value as OccupantRelationship];
  }
  return labels.other;
}

/** Localized label for a reservation document type (reuses the wizard's
 * doc-type dictionary; "" and unknown codes degrade to the raw value). */
export function documentTypeLabel(
  value: ReservationDocumentType,
  t: Dictionary,
): string {
  const labels = t.reservations.wizard.documents.types as Record<string, string>;
  return labels[value] ?? value;
}

/** Document types that evidence a family / marital relationship (§16/§39). The
 * reservation details group these apart from identity documents so a marriage
 * contract or family record is never mistaken for the guest's own ID. */
export const RELATIONSHIP_PROOF_DOC_TYPES: ReservationDocumentType[] = [
  "marriage_contract",
  "family_book",
  "family_statement",
];

/** True when a document is a relationship / family proof rather than an
 * identity document (used to split the details documents list into groups). */
export function isRelationshipProofDoc(docType: ReservationDocumentType): boolean {
  return RELATIONSHIP_PROOF_DOC_TYPES.includes(docType);
}

/** A payment tendered in a currency OTHER than the reservation/base currency —
 * i.e. it carries a real FX snapshot (original amount + rate + direction) worth
 * displaying (§29). Mirrors the wizard's recorded-payments check so the read UI
 * and the print slip stay consistent. Money values are decimal strings — never
 * parseFloat; this only compares currency codes and null. */
export function isForeignPayment(
  payment: Pick<Payment, "payment_currency" | "currency" | "original_amount">,
  baseCurrency: string,
): boolean {
  const payCurrency = payment.currency || baseCurrency;
  return (
    payment.payment_currency !== "" &&
    payment.payment_currency !== payCurrency &&
    payment.original_amount !== null
  );
}

/** Human label for a foreign payment's FX rate direction (§29). `rate_basis` is
 * a plain backend string — canonically `"base_per_payment"` (base = payment ×
 * rate) or `"payment_per_base"` (base = payment ÷ rate). Reuses the wizard's FX
 * selector labels so the read UI and the print slip stay consistent with the
 * BookingStep dropdown; an empty/unknown basis returns "" so the caller can skip
 * the separator honestly. */
export function fxDirectionLabel(
  rateBasis: string,
  booking: Pick<
    Dictionary["reservations"]["wizard"]["booking"],
    "rateBasisOptions"
  >,
): string {
  const options = booking.rateBasisOptions;
  if (rateBasis === "base_per_payment") return options.base_per_payment;
  if (rateBasis === "payment_per_base") return options.payment_per_base;
  return "";
}

/** Compose a companion's display name from the structured snapshot parts,
 * falling back to the localized generic row label when no name is stored. */
export function occupantDisplayName(
  occupant: Pick<
    ReservationOccupant,
    "first_name" | "father_name" | "last_name"
  >,
  t: Dictionary,
): string {
  const name = [occupant.first_name, occupant.father_name, occupant.last_name]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" ");
  return name || t.reservations.wizard.companions.adultRow;
}

/** PRINT-ONLY companion name: first + last, WITHOUT the father name (F2/§17). The
 * printed customer slip never shows a father name for the primary guest, so the
 * companion rows follow the same policy for consistency. Distinct from
 * `occupantDisplayName` (which composes the father name) so the on-screen details
 * are unaffected. */
export function occupantPrintName(
  occupant: Pick<ReservationOccupant, "first_name" | "last_name">,
  t: Dictionary,
): string {
  const name = [occupant.first_name, occupant.last_name]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" ");
  return name || t.reservations.wizard.companions.adultRow;
}
