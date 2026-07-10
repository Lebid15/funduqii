import type { ReservationListParams } from "@/lib/api/reservations";

/**
 * The reservations section's seven views (owner reorg): every view is a
 * FILTERED slice of the same list — reservations only, never stays or
 * check-ins. "Today" means CREATED today and "future" means arriving after
 * the hotel business date — both computed server-side in the hotel's
 * timezone (read-only list filters).
 */
export type ReservationView =
  | "all"
  | "today"
  | "website"
  | "future"
  | "pending"
  | "confirmed"
  | "closed";

export const RESERVATION_VIEWS: ReservationView[] = [
  "all",
  "today",
  "website",
  "future",
  "pending",
  "confirmed",
  "closed",
];

export const VIEW_PARAMS: Record<ReservationView, ReservationListParams> = {
  all: {},
  today: { created_today: "true" },
  website: { source: "public_website" },
  future: { upcoming: "true" },
  pending: { status: "held" },
  confirmed: { status: "confirmed" },
  closed: { statuses: "cancelled,expired" },
};

/** Views whose status is fixed by definition — the status filter is hidden. */
export const STATUS_BOUND_VIEWS: ReservationView[] = [
  "pending",
  "confirmed",
  "closed",
];
