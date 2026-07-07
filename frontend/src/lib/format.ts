/** Small presentation helpers shared across platform pages. */
import type { BadgeTone } from "@/components/ui";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/config";
import type { HotelStatus, SubscriptionStatus } from "@/lib/api/types";

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
