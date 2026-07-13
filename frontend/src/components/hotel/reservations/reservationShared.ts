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
import type { ReservationSource } from "@/lib/api/types";
import type { Dictionary } from "@/lib/i18n/dictionaries";

/** SOURCE badge (direct / phone / walk_in / public_website / other) — tone +
 * icon, never colour alone (WCAG). The public website is the only highlighted
 * source; everything else is neutral. */
export function sourceTone(source: ReservationSource): BadgeTone {
  return source === "public_website" ? "info" : "neutral";
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
