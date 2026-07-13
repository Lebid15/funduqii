/**
 * Client-side guests API (Phase 7). Calls the same-origin hotel BFF proxy
 * (`/api/hotel/...`); the proxy attaches auth + hotel context server-side.
 */
import { hotelJson } from "./hotelFetch";
import type {
  Guest,
  GuestDeleteResult,
  GuestDirectoryRow,
  GuestLookupResult,
  GuestProfile,
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

export function createGuest(body: GuestWriteBody): Promise<Guest> {
  return hotelJson<Guest>("/guests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

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

/** The guests-SECTION list: only guests with >= 1 real stay + derived stats. */
export function listGuestDirectory(
  params?: GuestListParams,
): Promise<PaginatedResponse<GuestDirectoryRow>> {
  return hotelJson<PaginatedResponse<GuestDirectoryRow>>(
    `/guests/directory${toQuery(params)}`,
  );
}

/** The central read-only guest profile (stats + stay history + links). */
export function getGuestProfile(id: number): Promise<GuestProfile> {
  return hotelJson<GuestProfile>(`/guests/${id}/profile`);
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
