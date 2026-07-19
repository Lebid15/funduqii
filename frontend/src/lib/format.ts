/** Small presentation helpers shared across platform pages. */
import type { BadgeTone } from "@/components/ui";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/config";
import type {
  EntitlementState,
  FolioStatus,
  HandoverStatus,
  HotelStatus,
  HousekeepingStatus,
  InvoiceStatus,
  LostFoundStatus,
  LostReportStatus,
  MaintenanceStatus,
  OperationPriority,
  PostingStatus,
  ReservationStatus,
  RoomStatus,
  ServiceOrderStatus,
  ShiftStatus,
  StayStatus,
  SubscriptionStatus,
} from "@/lib/api/types";

/** Two-letter initials from a full name (for avatars). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Locale-aware date formatting; returns an em dash for missing values. */
export function formatDate(iso: string | null, locale: Locale): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function hotelStatusTone(status: HotelStatus): BadgeTone {
  switch (status) {
    case "active":
      return "success";
    case "suspended":
      return "danger";
    default:
      return "neutral";
  }
}

export function hotelStatusLabel(status: HotelStatus, t: Dictionary): string {
  switch (status) {
    case "active":
      return t.hotels.statusActive;
    case "suspended":
      return t.hotels.statusSuspended;
    default:
      return t.hotels.statusSetup;
  }
}

export function subscriptionStatusTone(status: SubscriptionStatus): BadgeTone {
  switch (status) {
    case "active":
      return "success";
    case "trial":
      return "info";
    case "past_due":
      return "warning";
    case "cancelled":
    case "expired":
      return "neutral";
    default:
      return "neutral";
  }
}

export function subscriptionStatusLabel(
  status: SubscriptionStatus,
  t: Dictionary,
): string {
  switch (status) {
    case "active":
      return t.subscriptions.statusActive;
    case "trial":
      return t.subscriptions.statusTrial;
    case "past_due":
      return t.subscriptions.statusPastDue;
    case "expired":
      return t.subscriptions.statusExpired;
    case "cancelled":
      return t.subscriptions.statusCancelled;
    default:
      return status;
  }
}

export function roomStatusTone(status: RoomStatus): BadgeTone {
  switch (status) {
    case "available":
      return "success";
    case "dirty":
      return "warning";
    case "cleaning":
      return "info";
    case "maintenance":
      return "danger";
    default:
      return "neutral";
  }
}

export function roomStatusLabel(status: RoomStatus, t: Dictionary): string {
  return t.rooms.status[status];
}

/**
 * Localised guest-capacity phrase (never a raw "1–1" / "2–4" range).
 * - `base === max` → a properly-pluralised phrase (Arabic singular/dual/plural,
 *   English 1 vs N, Turkish invariant noun).
 * - `base !== max` → an "up to N guests" phrase keyed off `max`.
 * The count is rendered with the locale's own numerals (matches formatMoney).
 */
export function formatCapacity(
  base: number,
  max: number,
  t: Dictionary,
  locale: Locale,
): string {
  const c = t.rooms.board.capacityGuests;
  const num = (n: number) => new Intl.NumberFormat(locale).format(n);
  if (base !== max) return c.upTo.replace("{n}", num(max));
  if (base <= 1) return c.one;
  if (base === 2) return c.two;
  return c.few.replace("{n}", num(base));
}

export function reservationStatusTone(status: ReservationStatus): BadgeTone {
  switch (status) {
    case "confirmed":
      return "success";
    case "held":
      return "warning";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function reservationStatusLabel(
  status: ReservationStatus,
  t: Dictionary,
): string {
  return t.reservations.status[status];
}

export function stayStatusTone(status: StayStatus): BadgeTone {
  switch (status) {
    case "in_house":
      return "success";
    case "checked_out":
      return "neutral";
    default:
      return "danger";
  }
}

export function stayStatusLabel(status: StayStatus, t: Dictionary): string {
  return t.frontDesk.status[status];
}

/** Format a decimal-string money amount with its currency, locale-aware. */
export function formatMoney(
  amount: string | number | null,
  currency: string,
  locale: Locale,
): string {
  const value = Number(amount ?? 0);
  // Absent currency = MISSING DATA, not a fabricated default (owner §): render a
  // plain localised number with NO currency symbol — never invent "USD".
  if (!currency) {
    return new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
    }).format(value);
  } catch {
    // Unknown/invalid currency code: keep the amount + the raw code, never USD.
    return `${value.toFixed(2)} ${currency}`.trim();
  }
}

export function folioStatusTone(status: FolioStatus): BadgeTone {
  switch (status) {
    case "open":
      return "info";
    case "closed":
      return "success";
    default:
      return "danger";
  }
}

export function invoiceStatusTone(status: InvoiceStatus): BadgeTone {
  switch (status) {
    case "issued":
      return "success";
    case "draft":
      return "warning";
    default:
      return "danger";
  }
}

export function postingStatusTone(status: PostingStatus): BadgeTone {
  return status === "posted" ? "success" : "danger";
}

export function formatDateTime(iso: string | null, locale: Locale): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function serviceOrderStatusTone(status: ServiceOrderStatus): BadgeTone {
  switch (status) {
    case "submitted":
      return "info";
    case "preparing":
      return "warning";
    case "ready":
      return "primary";
    case "delivered":
      return "success";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function housekeepingStatusTone(status: HousekeepingStatus): BadgeTone {
  switch (status) {
    case "pending":
      return "warning";
    case "assigned":
      return "info";
    case "in_progress":
      return "primary";
    case "awaiting_inspection":
      return "warning";
    case "completed":
      return "success";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function maintenanceStatusTone(status: MaintenanceStatus): BadgeTone {
  switch (status) {
    case "open":
      return "warning";
    case "assigned":
      return "info";
    case "in_progress":
      return "primary";
    case "resolved":
      return "success";
    case "closed":
      return "neutral";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function lostFoundStatusTone(status: LostFoundStatus): BadgeTone {
  switch (status) {
    case "found":
      return "warning";
    case "stored":
      return "info";
    case "claimed":
      return "primary";
    case "returned":
      return "success";
    case "disposed":
      return "danger";
    default:
      return "neutral";
  }
}

export function lostReportStatusTone(status: LostReportStatus): BadgeTone {
  switch (status) {
    case "open":
      return "info";
    case "searching":
      return "warning";
    case "matched":
      return "primary";
    case "returned":
      return "success";
    case "closed_unfound":
      return "neutral";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function shiftStatusTone(status: ShiftStatus): BadgeTone {
  switch (status) {
    case "open":
      return "success";
    case "closing":
      return "warning";
    case "closed":
      return "neutral";
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function handoverStatusTone(status: HandoverStatus): BadgeTone {
  switch (status) {
    case "draft":
      return "neutral";
    case "submitted":
      return "warning";
    case "accepted":
      return "success";
    case "rejected":
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function operationPriorityTone(priority: OperationPriority): BadgeTone {
  switch (priority) {
    case "urgent":
      return "danger";
    case "high":
      return "warning";
    case "low":
      return "neutral";
    default:
      return "info";
  }
}

/** Translate a settings-audit section key (§9.17). Falls back to the raw key so
 * a future section never renders blank. */
export function settingsSectionLabel(section: string, t: Dictionary): string {
  const s = t.hotel.settings;
  switch (section) {
    case "identity":
      return s.sectionIdentity;
    case "localization":
      return s.sectionLocalization;
    case "contact":
      return s.sectionContact;
    case "location":
      return s.sectionLocation;
    case "policies":
      return s.sectionPolicies;
    case "operational":
      return s.sectionDefaults;
    case "public":
      return s.sectionPublic;
    case "all":
      return s.sectionAll;
    case "platform":
      return s.sectionPlatformGeneral;
    case "public_site":
      return s.sectionPublicSiteAdmin;
    default:
      return section;
  }
}

export function entitlementStateTone(state: EntitlementState): BadgeTone {
  switch (state) {
    case "over_limit":
      return "danger";
    case "limit_reached":
      return "warning";
    case "nearing_limit":
      return "warning";
    default:
      return "success";
  }
}

export function entitlementStateLabel(
  state: EntitlementState,
  t: Dictionary,
): string {
  switch (state) {
    case "over_limit":
      return t.entitlements.stateOver;
    case "limit_reached":
      return t.entitlements.stateReached;
    case "nearing_limit":
      return t.entitlements.stateNearing;
    default:
      return t.entitlements.stateNormal;
  }
}

export function billingCycleLabel(cycle: string, t: Dictionary): string {
  switch (cycle) {
    case "yearly":
      return t.plans.cycleYearly;
    case "custom":
      return t.plans.cycleCustom;
    default:
      return t.plans.cycleMonthly;
  }
}
