/**
 * Client-side API for the PUBLIC website (Phase 15).
 *
 * Calls the anonymous same-origin proxy (`/api/public/...`) — no session, no
 * tokens, no hotel context. Everything returned here is visitor-safe by
 * construction on the Django side. The manage token is held only in the
 * visitor's browser (shown once at booking time); it is never stored here.
 */
import type { ApiError } from "./client";

const PROXY_BASE = "/api/public";

async function publicFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${PROXY_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      // no JSON body
    }
    const record =
      body && typeof body === "object" ? (body as Record<string, unknown>) : {};
    throw {
      status: response.status,
      code: typeof record.code === "string" ? record.code : "error",
      message:
        typeof record.message === "string"
          ? record.message
          : response.statusText,
      details: record.details,
    } as ApiError;
  }
  return (await response.json()) as T;
}

// --- DTOs (mirror /api/v1/public/ responses) --------------------------------

export interface PublicHotelCard {
  slug: string;
  name: string;
  short_description: string;
  city: string;
  country: string;
  star_rating: number | null;
  featured: boolean;
  booking_enabled: boolean;
  cover_url: string | null;
  logo_url: string | null;
}

export interface PublicRoomType {
  id: number;
  name: string;
  description: string;
  base_capacity: number;
  max_capacity: number;
  bed_type: string;
  base_price: string | null;
  currency: string;
}

export interface PublicHotelDetail extends PublicHotelCard {
  description: string;
  address: string;
  area: string;
  phone: string;
  whatsapp: string;
  email: string;
  website: string;
  check_in_time: string | null;
  check_out_time: string | null;
  cancellation_policy: string;
  terms: string;
  min_nights: number | null;
  max_nights: number | null;
  requires_confirmation: boolean;
  gallery: { url: string; alt: string }[];
  room_types: PublicRoomType[];
}

export interface PublicTypeAvailability extends PublicRoomType {
  available_quantity: number;
  can_book: boolean;
}

export interface PublicAvailability {
  check_in: string;
  check_out: string;
  booking_enabled: boolean;
  room_types: PublicTypeAvailability[];
}

export interface PublicBookingBody {
  check_in: string;
  check_out: string;
  room_type: number;
  rooms_count: number;
  adults: number;
  children: number;
  guest_name: string;
  guest_phone: string;
  guest_email?: string;
  guest_nationality?: string;
  special_requests?: string;
  accept_terms: boolean;
}

export interface PublicBooking {
  reference: string;
  status: string;
  requires_confirmation: boolean;
  hotel_name: string;
  hotel_slug: string;
  check_in_date: string;
  check_out_date: string;
  nights: number;
  room_type_name: string;
  rooms_count: number;
  adults: number;
  children: number;
  guest_name: string;
  guest_phone: string;
  guest_email: string;
  special_requests: string;
  cancel_requested_at: string | null;
  created_at: string;
  /** Present ONLY on the creation response — shown to the visitor once. */
  manage_token?: string;
}

// --- Calls -------------------------------------------------------------------

export function listPublicHotels(params?: {
  q?: string;
  city?: string;
  country?: string;
}): Promise<{ count: number; results: PublicHotelCard[] }> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.city) search.set("city", params.city);
  if (params?.country) search.set("country", params.country);
  const qs = search.toString();
  return publicFetch(`/hotels${qs ? `?${qs}` : ""}`);
}

export function getPublicHotel(slug: string): Promise<PublicHotelDetail> {
  return publicFetch(`/hotels/${slug}`);
}

export function getPublicAvailability(
  slug: string,
  checkIn: string,
  checkOut: string,
): Promise<PublicAvailability> {
  return publicFetch(
    `/hotels/${slug}/availability?check_in=${checkIn}&check_out=${checkOut}`,
  );
}

export function createPublicBooking(
  slug: string,
  body: PublicBookingBody,
): Promise<PublicBooking> {
  return publicFetch(`/hotels/${slug}/bookings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getPublicBooking(
  reference: string,
  token: string,
): Promise<PublicBooking> {
  return publicFetch(
    `/bookings/${encodeURIComponent(reference)}?token=${encodeURIComponent(token)}`,
  );
}

export function requestPublicCancellation(
  reference: string,
  token: string,
  reason: string,
): Promise<PublicBooking> {
  return publicFetch(`/bookings/${encodeURIComponent(reference)}/cancel-request`, {
    method: "POST",
    body: JSON.stringify({ token, reason }),
  });
}
