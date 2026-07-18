/**
 * Client-side guests API (Phase 7). Calls the same-origin hotel BFF proxy
 * (`/api/hotel/...`); the proxy attaches auth + hotel context server-side.
 */
import { hotelJson } from "./hotelFetch";
import type {
  Guest,
  GuestChangeLogRow,
  GuestDeleteResult,
  GuestDirectoryRow,
  GuestDocumentRow,
  GuestLookupResult,
  GuestProfile,
  GuestReservationRow,
  GuestStayRow,
  PaginatedResponse,
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

export interface GuestListParams {
  search?: string;
  is_active?: string;
  page?: number;
  page_size?: number;
}

/** Plain pagination params for the central-identity sub-lists. */
export interface GuestPageParams {
  page?: number;
  page_size?: number;
}

export function listGuests(
  params?: GuestListParams,
): Promise<PaginatedResponse<Guest>> {
  return hotelJson<PaginatedResponse<Guest>>(`/guests${toQuery(params)}`);
}

export type GuestWriteBody = Partial<
  Pick<
    Guest,
    | "full_name"
    | "first_name"
    | "last_name"
    | "father_name"
    | "mother_name"
    | "phone"
    | "email"
    | "no_email"
    | "nationality"
    | "national_id"
    | "document_type"
    | "document_number"
    | "date_of_birth"
    | "gender"
    | "address"
    | "notes"
    | "is_active"
  >
>;

/* GUESTS-CLOSURE Decision 9 — standalone guest creation was removed: a guest is
 * now resolved/created CENTRALLY by the reservation + check-in flows from the
 * booking's guest snapshot. `POST /guests/` is `405 Method Not Allowed`, so no
 * `createGuest` client exists. `GuestWriteBody` remains for `updateGuest`. */

export function updateGuest(id: number, body: GuestWriteBody): Promise<Guest> {
  return hotelJson<Guest>(`/guests/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Delete hardening: the backend answers `deleted` or `deactivated`. */
export function deleteGuest(id: number): Promise<GuestDeleteResult> {
  return hotelJson<GuestDeleteResult>(`/guests/${id}`, { method: "DELETE" });
}

/** The guests-SECTION list: only guests with >= 1 real stay + derived stats.
 * `search` is forwarded verbatim as the `search` query param; the backend does
 * the matching (an EXACT `national_id` match is supported server-side, and the
 * document search is gated behind guests.view_sensitive_data). The client never
 * interprets the term. */
export function listGuestDirectory(
  params?: GuestListParams,
): Promise<PaginatedResponse<GuestDirectoryRow>> {
  return hotelJson<PaginatedResponse<GuestDirectoryRow>>(
    `/guests/directory${toQuery(params)}`,
  );
}

/** The central read-only guest profile (stats + stay history + links + the
 * GUESTS-CLOSURE `needs_review` flag and `upcoming_reservations`). */
export function getGuestProfile(id: number): Promise<GuestProfile> {
  return hotelJson<GuestProfile>(`/guests/${id}/profile`);
}

/* --- GUESTS-CLOSURE central-identity paginated sub-lists -------------------- *
 * Each returns a DRF PageNumberPagination envelope. RBAC is re-checked
 * server-side (documents additionally require reservation_documents.view). */

/** GET guests/<pk>/stays/ — the guest's stays across the hotel (paginated). */
export function listGuestStays(
  id: number,
  params?: GuestPageParams,
): Promise<PaginatedResponse<GuestStayRow>> {
  return hotelJson<PaginatedResponse<GuestStayRow>>(
    `/guests/${id}/stays${toQuery(params)}`,
  );
}

/** GET guests/<pk>/reservations/ — the guest's reservations (paginated). */
export function listGuestReservations(
  id: number,
  params?: GuestPageParams,
): Promise<PaginatedResponse<GuestReservationRow>> {
  return hotelJson<PaginatedResponse<GuestReservationRow>>(
    `/guests/${id}/reservations${toQuery(params)}`,
  );
}

/** GET guests/<pk>/documents/ — the guest's uploaded documents (paginated).
 * Requires guests.view AND reservation_documents.view. */
export function listGuestDocuments(
  id: number,
  params?: GuestPageParams,
): Promise<PaginatedResponse<GuestDocumentRow>> {
  return hotelJson<PaginatedResponse<GuestDocumentRow>>(
    `/guests/${id}/documents${toQuery(params)}`,
  );
}

/** GET guests/<pk>/change-log/ — the guest's change-event history (paginated). */
export function listGuestChangeLog(
  id: number,
  params?: GuestPageParams,
): Promise<PaginatedResponse<GuestChangeLogRow>> {
  return hotelJson<PaginatedResponse<GuestChangeLogRow>>(
    `/guests/${id}/change-log${toQuery(params)}`,
  );
}

export function setGuestVip(id: number, vip: boolean): Promise<Guest> {
  return hotelJson<Guest>(`/guests/${id}/vip`, {
    method: "POST",
    body: JSON.stringify({ vip }),
  });
}

export function blockGuest(id: number, reason: string): Promise<Guest> {
  return hotelJson<Guest>(`/guests/${id}/block`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function unblockGuest(id: number, note = ""): Promise<Guest> {
  return hotelJson<Guest>(`/guests/${id}/unblock`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

/** Smart lookup for the reservation form (RESERVATIONS-FORM-REWORK).
 * Exact-match, hotel-scoped, behind `guests.view`. Pass `national_id` and/or
 * `phone`; with neither the backend returns an empty result rather than
 * scanning. Callers should DEBOUNCE input. `national_id` is masked per
 * `guests.view_sensitive_data`. */
export interface GuestLookupParams {
  national_id?: string;
  phone?: string;
}

export function lookupGuest(
  params: GuestLookupParams,
): Promise<GuestLookupResult> {
  return hotelJson<GuestLookupResult>(`/guests/lookup${toQuery(params)}`);
}
