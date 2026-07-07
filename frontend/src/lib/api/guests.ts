/**
 * Client-side guests API (Phase 7). Calls the same-origin hotel BFF proxy
 * (`/api/hotel/...`); the proxy attaches auth + hotel context server-side.
 */
import { hotelJson } from "./hotelFetch";
import type { Guest, PaginatedResponse } from "./types";

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
    | "phone"
    | "email"
    | "nationality"
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

export function deleteGuest(id: number): Promise<void> {
  return hotelJson<void>(`/guests/${id}`, { method: "DELETE" });
}
