/**
 * Client-side stays / front-desk API (Phase 7). Calls the same-origin hotel BFF
 * proxy. The backend is the source of truth for check-in/out rules — these
 * helpers never decide admissibility themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  PaginatedResponse,
  Reservation,
  Stay,
  StayStatusLogEntry,
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

export interface StayListParams {
  status?: string;
  room?: number;
  planned_check_out_date?: string;
  search?: string;
  page?: number;
}

export function listStays(
  params?: StayListParams,
): Promise<PaginatedResponse<Stay>> {
  return hotelJson<PaginatedResponse<Stay>>(`/stays${toQuery(params)}`);
}

export function listCurrentResidents(): Promise<PaginatedResponse<Stay>> {
  return hotelJson<PaginatedResponse<Stay>>("/stays/current");
}

export function listArrivalsToday(): Promise<Reservation[]> {
  return hotelJson<Reservation[]>("/stays/arrivals-today");
}

export function listDeparturesToday(): Promise<PaginatedResponse<Stay>> {
  return hotelJson<PaginatedResponse<Stay>>("/stays/departures-today");
}

export function getStay(id: number): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}`);
}

export function getStayLogs(id: number): Promise<StayStatusLogEntry[]> {
  return hotelJson<StayStatusLogEntry[]>(`/stays/${id}/logs`);
}

export interface CheckInBody {
  reservation: number;
  reservation_line?: number | null;
  room?: number | null;
  primary_guest: number;
  companions?: number[];
  check_in_notes?: string;
}

export function checkIn(body: CheckInBody): Promise<Stay> {
  return hotelJson<Stay>("/stays/check-in", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface CheckOutBody {
  check_out_notes?: string;
  checkout_reason?: string;
}

export function checkOut(id: number, body: CheckOutBody = {}): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}/check-out`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
