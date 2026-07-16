/**
 * Client-side reservations & availability API (Phase 6).
 *
 * Calls the same-origin hotel BFF proxy (`/api/hotel/...`); the proxy attaches
 * auth + hotel context server-side. Nothing sensitive is handled here. The
 * backend is the source of truth for availability and overbooking — these
 * helpers never decide bookability on their own.
 */
import type { ApiError } from "./client";
import { hotelFetch, hotelJson } from "./hotelFetch";
import type {
  ImmediateCheckInResult,
  OccupantRelationship,
  PaginatedResponse,
  Reservation,
  ReservationDepositBody,
  ReservationDepositResult,
  ReservationDocument,
  ReservationFinancialSummary,
  ReservationOverview,
  ReservationStatusLogEntry,
  RoomAvailabilityRow,
  TypeAvailability,
} from "./types";

/** Same-origin BFF prefix (mirrors `hotelFetch`). Used only for the document
 * blob fetch, which reads raw bytes rather than JSON. */
const PROXY_BASE = "/api/hotel";

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
  /** Comma-separated multi-status (e.g. "cancelled,expired"). */
  statuses?: string;
  source?: string;
  room_type?: number;
  room?: number;
  date_from?: string;
  date_to?: string;
  created_from?: string;
  created_to?: string;
  /** Business-date aware (hotel timezone) — created on the hotel's today. */
  created_today?: "true";
  /** Arrival strictly after the hotel business date. */
  upcoming?: "true";
  /** Pending public-website cancel requests (still held/confirmed). */
  cancel_requested?: "true";
  search?: string;
  page?: number;
  page_size?: number;
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

/** RESERVATIONS-AUTO-ROOM: how the physical room is chosen for the reservation.
 * `"automatic"` → the backend deterministically assigns an available room inside
 * the atomic create (the client MUST NOT pin one); `"manual"` → the client sends
 * the chosen room id and the backend validates it (never a silent swap). Absent =
 * legacy behaviour (the caller's room, or none, is kept as-is). */
export type RoomAssignmentMode = "automatic" | "manual";

export interface ReservationLineBody {
  room_type: number;
  room?: number | null;
  /** RESERVATIONS-AUTO-ROOM: optional floor preference. In automatic mode it
   * narrows the deterministic picker to this floor; in manual mode it must match
   * the pinned room's floor. Request-only — never persisted on the line. */
  floor?: number | null;
  quantity: number;
  adults?: number | null;
  children?: number | null;
  notes?: string;
}

/** One adult companion on a reservation write (RESERVATIONS-FORM-REWORK).
 * `guest` optionally links to a central Guest (resolved + hotel-scoped
 * server-side); when omitted the structured identity is stored inline. Children
 * remain a plain count on `ReservationCreateBody.children`. */
export interface ReservationOccupantBody {
  guest?: number | null;
  first_name?: string;
  last_name?: string;
  father_name?: string;
  mother_name?: string;
  national_id?: string;
  nationality?: string;
  date_of_birth?: string | null;
  relationship: OccupantRelationship;
}

export interface ReservationCreateBody {
  status: "held" | "confirmed";
  source?: string;
  booking_kind?: "instant" | "future";
  check_in_date: string;
  check_out_date: string;
  expected_arrival_time?: string | null;
  /** Optional link to the central guest directory (set when the primary guest
   * was matched via lookup). The structured snapshot below is frozen at booking
   * time and is never auto-rewritten by later guest edits. */
  primary_guest?: number | null;
  primary_guest_name: string;
  primary_guest_phone?: string;
  primary_guest_email?: string;
  primary_guest_nationality?: string;
  primary_guest_document_type?: string;
  primary_guest_document_number?: string;
  primary_guest_first_name?: string;
  primary_guest_last_name?: string;
  primary_guest_father_name?: string;
  primary_guest_mother_name?: string;
  primary_guest_national_id?: string;
  primary_guest_date_of_birth?: string | null;
  /** Derived server-side from `occupants` (1 primary + named adult companions);
   * send it or omit it — the server reconciles. */
  adults: number;
  children: number;
  notes?: string;
  special_requests?: string;
  booking_channel_name?: string;
  expected_payment_method?: string;
  hold_expires_at?: string | null;
  /** Named adult companions. Total persons = 1 + occupants + children. */
  occupants?: ReservationOccupantBody[];
  lines: ReservationLineBody[];
  /** RESERVATIONS-AUTO-ROOM: request-only assignment mode. `"automatic"` → the
   * backend picks the room (send room_type + floor criteria, never a room id);
   * `"manual"` → the line pins the chosen room. Omitted = legacy behaviour. */
  room_assignment_mode?: RoomAssignmentMode;
  /** RESERVATIONS-DEFERRED-CORRECTIONS §7.3 — optional key that PINS a number
   * previously reserved via `reserveReservationNumber` (on form open). The server
   * reuses that reserved number for the SAME (hotel, key); omitted → it allocates
   * a fresh number. The FE NEVER generates or guesses a reservation number. */
  idempotency_key?: string;
}

export function createReservation(
  body: ReservationCreateBody,
): Promise<Reservation> {
  return hotelJson<Reservation>("/reservations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** RESERVATIONS-DEFERRED-CORRECTIONS §7.3 — reserve a REAL reservation number up
 * front (on form open) so staff see the actual number instead of a placeholder.
 * The server allocates + holds a numbered DRAFT keyed by (hotel, idempotency_key):
 * repeat calls with the SAME key return the SAME number, so a StrictMode
 * double-mount / re-render / retry never burns two numbers. Passing that same
 * `idempotency_key` to `createReservation` PINS this number onto the created
 * reservation. Gated by `reservations.create`; hotel-scoped server-side. */
export interface ReserveReservationNumberResult {
  reservation_number: string;
  draft_id: number;
  expires_at: string;
}

export function reserveReservationNumber(
  idempotencyKey: string,
): Promise<ReserveReservationNumberResult> {
  return hotelJson<ReserveReservationNumberResult>(
    "/reservations/reserve-number",
    { method: "POST", body: JSON.stringify({ idempotency_key: idempotencyKey }) },
  );
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

/** Mark an expected arrival as a no-show (§29) — a mandatory reason. */
export function markNoShow(
  id: number,
  reason: string,
): Promise<Reservation> {
  return hotelJson<Reservation>(`/reservations/${id}/no-show`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function getReservationLogs(
  id: number,
): Promise<ReservationStatusLogEntry[]> {
  return hotelJson<ReservationStatusLogEntry[]>(`/reservations/${id}/logs`);
}

// --- Reservation money (RESERVATIONS-FORM-UX-CORRECTION §27/§31) -------------

/** Record a pre-arrival DEPOSIT on a future/held/confirmed reservation that has
 * NO stay yet (§27). `POST /reservations/<id>/payments/` mirrors the immediate
 * check-in deposit shape: a base-currency deposit sends `amount`; a foreign one
 * sends `original_amount` + `exchange_rate` (+ optional `rate_basis`) and the
 * backend DERIVES the base amount onto the reservation's ONE folio (reused at
 * check-in — no duplicate ledger). Requires `finance.payment_create`
 * (+ `exchange_rate.override` for a manual foreign rate); the backend enforces
 * it. Returns the created payment and the refreshed derived financial summary. */
export function createReservationDeposit(
  reservationId: number,
  body: ReservationDepositBody,
): Promise<ReservationDepositResult> {
  return hotelJson<ReservationDepositResult>(
    `/reservations/${reservationId}/payments`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** The DERIVED financial summary for a saved reservation (§26/§31/§35/§39):
 * total, paid, remaining, currency and the payments list (with FX). The money
 * block is masked server-side for callers without `finance.view`. Read-only —
 * nothing is created and the balance is re-derived, never stored. */
export function getReservationFinancialSummary(
  id: number,
): Promise<ReservationFinancialSummary> {
  return hotelJson<ReservationFinancialSummary>(
    `/reservations/${id}/financial-summary`,
  );
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

// --- Per-room availability (RESERVATIONS-FORM-REWORK) -----------------------

export interface RoomAvailabilityParams {
  check_in: string;
  check_out: string;
  floor?: number;
  room_type?: number;
}

/** Candidate rooms for a period with a per-room `available` flag. The backend
 * wraps the rows in `{ results }`; this unwraps to the array. Availability and
 * pricing are backend-authoritative — never decide bookability client-side. */
export function getRoomAvailability(
  params: RoomAvailabilityParams,
): Promise<RoomAvailabilityRow[]> {
  return hotelJson<{ results: RoomAvailabilityRow[] }>(
    `/reservations/room-availability${toQuery(params)}`,
  ).then((data) => data.results);
}

// --- Reservation guest documents (RESERVATIONS-FORM-REWORK) -----------------

/** List a reservation's documents (metadata only). Behind
 * `reservation_documents.view`. */
export function listReservationDocuments(
  reservationId: number,
): Promise<ReservationDocument[]> {
  return hotelJson<ReservationDocument[]>(
    `/reservations/${reservationId}/documents`,
  );
}

/** Upload a document (multipart: `doc_type`, `number?`, `occupant?`, and at
 * least one of `front_file`/`back_file`). Behind `reservation_documents.upload`.
 * No Content-Type header — the browser sets the multipart boundary. */
export function uploadReservationDocument(
  reservationId: number,
  formData: FormData,
): Promise<ReservationDocument> {
  return hotelFetch<ReservationDocument>(
    `/reservations/${reservationId}/documents`,
    { method: "POST", body: formData },
  );
}

/** Replace a document's file(s) and/or metadata (multipart). Behind
 * `reservation_documents.replace`. */
export function replaceReservationDocument(
  docId: number,
  formData: FormData,
): Promise<ReservationDocument> {
  return hotelFetch<ReservationDocument>(
    `/reservations/documents/${docId}`,
    { method: "PATCH", body: formData },
  );
}

/**
 * Fetch a document side's raw bytes through the authenticated BFF and return an
 * object URL for an `<img>`/PDF viewer. The CALLER owns the URL and MUST call
 * `URL.revokeObjectURL` when done (e.g. on unmount). Reads bytes directly
 * (not via `hotelFetch`, which parses JSON); a 401 still bounces to /login.
 */
export async function getReservationDocumentBlobUrl(
  docId: number,
  side: "front" | "back",
): Promise<string> {
  const response = await fetch(
    `${PROXY_BASE}/reservations/documents/${docId}/${side}`,
  );
  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
    throw { status: 401, code: "session_expired", message: "" } as ApiError;
  }
  if (!response.ok) {
    throw {
      status: response.status,
      code: "error",
      message: response.statusText,
    } as ApiError;
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

// --- Immediate atomic check-in (RESERVATIONS-FORM-REWORK) -------------------

/** Body for `POST /stays/immediate-check-in/`. The reservation fields reuse the
 * normal create body (lines / primary guest / occupants resolved identically);
 * `room` is the physical room to admit into, `line_index` picks the line when a
 * reservation has more than one, and `deposit` is an optional real payment. */
export interface ImmediateCheckInBody {
  reservation: ReservationCreateBody;
  room?: number | null;
  line_index?: number | null;
  check_in_notes?: string;
  deposit?: ReservationDepositBody | null;
}

/** Create a reservation AND check the guest in atomically (optionally taking a
 * deposit). Requires `reservations.create` + `stays.check_in` (+
 * `finance.payment_create` for a deposit, + `exchange_rate.override` for a
 * manual foreign-currency rate) — the backend enforces all of it. */
export function immediateCheckIn(
  body: ImmediateCheckInBody,
): Promise<ImmediateCheckInResult> {
  return hotelJson<ImmediateCheckInResult>("/stays/immediate-check-in", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
