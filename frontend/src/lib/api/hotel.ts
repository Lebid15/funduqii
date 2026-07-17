/**
 * Client-side hotel API.
 *
 * Client components call the same-origin hotel BFF proxy (`/api/hotel/...`),
 * which attaches the HttpOnly access token and the X-Hotel-ID context
 * server-side. No tokens or hotel ids are handled here. Text settings and media
 * are separate calls — saving settings never re-sends images.
 */
import { hotelFetch, hotelJson } from "./hotelFetch";
import type {
  AvailablePlansResponse,
  ChangeRequestKind,
  HotelMedia,
  HotelProfile,
  HotelSettings,
  MediaKind,
  SubscriptionChangeRequest,
} from "./types";

const request = hotelFetch;
const jsonRequest = hotelJson;

// --- Settings ---------------------------------------------------------------

export function getSettings(): Promise<HotelSettings> {
  return jsonRequest<HotelSettings>("/settings");
}

export function getProfile(): Promise<HotelProfile> {
  return jsonRequest<HotelProfile>("/profile");
}

export function updateSettings(
  body: Partial<HotelSettings>,
): Promise<HotelSettings> {
  return jsonRequest<HotelSettings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- Media ------------------------------------------------------------------

export function listMedia(kind?: MediaKind): Promise<HotelMedia[]> {
  const qs = kind ? `?kind=${kind}` : "";
  return jsonRequest<HotelMedia[]>(`/media${qs}`);
}

/** Upload an image as multipart/form-data (never base64). */
export function uploadMedia(
  kind: MediaKind,
  file: File,
  altText?: string,
): Promise<HotelMedia> {
  const form = new FormData();
  form.set("kind", kind);
  form.set("file", file);
  if (altText) form.set("alt_text", altText);
  // No Content-Type header — the browser sets the multipart boundary.
  return request<HotelMedia>("/media", { method: "POST", body: form });
}

export function updateMedia(
  id: number,
  body: { alt_text?: string; sort_order?: number; is_active?: boolean },
): Promise<HotelMedia> {
  return jsonRequest<HotelMedia>(`/media/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteMedia(id: number): Promise<void> {
  return jsonRequest<void>(`/media/${id}`, { method: "DELETE" });
}

// --- Subscription change requests (§8.4/§8.5) -------------------------------
// The hotel's only write access to the subscription lifecycle. The backend
// decides all eligibility; these calls just carry the manager's intent.

export function getAvailablePlans(): Promise<AvailablePlansResponse> {
  return jsonRequest<AvailablePlansResponse>("/subscription/plans");
}

export function listMyRequests(): Promise<SubscriptionChangeRequest[]> {
  return jsonRequest<SubscriptionChangeRequest[]>("/subscription/requests");
}

export function submitChangeRequest(body: {
  kind: ChangeRequestKind;
  requested_plan?: number;
  hotel_note?: string;
}): Promise<SubscriptionChangeRequest> {
  return jsonRequest<SubscriptionChangeRequest>("/subscription/requests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelMyRequest(
  id: number,
): Promise<SubscriptionChangeRequest> {
  return jsonRequest<SubscriptionChangeRequest>(
    `/subscription/requests/${id}/cancel`,
    { method: "POST", body: JSON.stringify({}) },
  );
}
