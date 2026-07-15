/**
 * Client-side stays / front-desk API (Phase 7). Calls the same-origin hotel BFF
 * proxy. The backend is the source of truth for check-in/out rules — these
 * helpers never decide admissibility themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  AdmissibleRoom,
  PaginatedResponse,
  Reservation,
  Stay,
  StayFolioSummary,
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

/** Rooms actually admissible for a reservation line (check-in dialog). */
export function listCheckInRooms(
  reservation: number,
  line: number,
): Promise<AdmissibleRoom[]> {
  return hotelJson<AdmissibleRoom[]>(
    `/stays/check-in-rooms${toQuery({ reservation, line })}`,
  );
}

export interface StayDateChangeBody {
  new_check_out_date: string;
  reason?: string;
}

export function extendStay(id: number, body: StayDateChangeBody): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}/extend`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function shortenStay(id: number, body: StayDateChangeBody): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}/shorten`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface MoveRoomBody {
  room: number;
  reason: string;
}

export function moveStayRoom(id: number, body: MoveRoomBody): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}/move-room`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Rooms a stay can move into right now (room-move dialog). */
export function listMoveCandidates(id: number): Promise<AdmissibleRoom[]> {
  return hotelJson<AdmissibleRoom[]>(`/stays/${id}/move-candidates`);
}

/** Open-folio balance + business-date context for the check-out dialog. */
export function getStayFolioSummary(id: number): Promise<StayFolioSummary> {
  return hotelJson<StayFolioSummary>(`/stays/${id}/folio-summary`);
}

/**
 * Post every room night that has become due by the hotel business date, then
 * return the refreshed folio summary (§24 owner correction). The checkout dialog
 * calls this on open so the front desk always settles the complete amount — the
 * folio is never missing a consumed night because the daily close has not run.
 * Idempotent; never posts a future night. Requires `stays.check_out`.
 */
export function ensureRoomCharges(id: number): Promise<StayFolioSummary> {
  return hotelJson<StayFolioSummary>(`/stays/${id}/ensure-room-charges`, {
    method: "POST",
    body: "{}",
  });
}

/** Counts for the six operational cards (§6/§50) — from the backend, one call. */
export interface StaysOverview {
  business_date: string;
  arriving_today: number;
  awaiting_check_in: number;
  checked_in_today: number;
  current_residents: number;
  departing_today: number;
  needs_attention: number;
}

export function getStaysOverview(): Promise<StaysOverview> {
  return hotelJson<StaysOverview>("/stays/overview");
}

/** Reverse a mistaken check-in (§30) — a mandatory reason. */
export function reverseCheckIn(
  id: number,
  body: { reason: string },
): Promise<Stay> {
  return hotelJson<Stay>(`/stays/${id}/reverse-check-in`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
