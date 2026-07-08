/**
 * Client-side reservations & availability API (Phase 6).
 *
 * Calls the same-origin hotel BFF proxy (`/api/hotel/...`); the proxy attaches
 * auth + hotel context server-side. Nothing sensitive is handled here. The
 * backend is the source of truth for availability and overbooking — these
 * helpers never decide bookability on their own.
 */
import { hotelJson } from "./hotelFetch";
import type {
  PaginatedResponse,
  Reservation,
  ReservationOverview,
  ReservationStatusLogEntry,
  TypeAvailability,
} from "./types";

function toQuery(params?: object): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

// --- Reservations -----------------------------------------------------------

export interface ReservationListParams {
  status?: string;
  room_type?: number;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
}

export function listReservations(
  params?: ReservationListParams,
): Promise<PaginatedResponse<Reservation>> {
  return hotelJson<PaginatedResponse<Reservation>>(
    `/reservations${toQuery(params)}`,
  );
}

export function getReservation(id: number): Promise<Reservation> {
  return hotelJson<Reservation>(`/reservations/${id}`);
}

export function getReservationOverview(): Promise<ReservationOverview> {
  return hotelJson<ReservationOverview>("/reservations/overview");
}

export interface ReservationLineBody {
  room_type: number;
  room?: number | null;
  quantity: number;
  adults?: number | null;
  children?: number | null;
  notes?: string;
}

export interface ReservationCreateBody {
  status: "held" | "confirmed";
  source?: string;
  booking_kind?: "instant" | "future";
  check_in_date: string;
  check_out_date: string;
  expected_arrival_time?: string | null;
  primary_guest_name: string;
  primary_guest_phone?: string;
  primary_guest_email?: string;
  primary_guest_nationality?: string;
  primary_guest_document_type?: string;
  primary_guest_document_number?: string;
  adults: number;
  children: number;
  notes?: string;
  special_requests?: string;
  booking_channel_name?: string;
  expected_payment_method?: string;
  hold_expires_at?: string | null;
  lines: ReservationLineBody[];
}

export function createReservation(
  body: ReservationCreateBody,
): Promise<Reservation> {
  return hotelJson<Reservation>("/reservations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type ReservationUpdateBody = Partial<
  Omit<ReservationCreateBody, "status">
>;

export function updateReservation(
  id: number,
  body: ReservationUpdateBody,
): Promise<Reservation> {
  return hotelJson<Reservation>(`/reservations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function confirmReservation(id: number): Promise<Reservation> {
  return hotelJson<Reservation>(`/reservations/${id}/confirm`, {
    method: "POST",
    body: "{}",
  });
}

export function cancelReservation(
  id: number,
  reason: string,
): Promise<Reservation> {
  return hotelJson<Reservation>(`/reservations/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function getReservationLogs(
  id: number,
): Promise<ReservationStatusLogEntry[]> {
  return hotelJson<ReservationStatusLogEntry[]>(`/reservations/${id}/logs`);
}

// --- Availability -----------------------------------------------------------

export interface AvailabilityParams {
  check_in_date: string;
  check_out_date: string;
  room_type?: number;
  adults?: number;
  children?: number;
}

export function checkAvailability(
  params: AvailabilityParams,
): Promise<{ results: TypeAvailability[] }> {
  return hotelJson<{ results: TypeAvailability[] }>(
    `/availability${toQuery(params)}`,
  );
}
