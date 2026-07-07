/**
 * Client-side hotel API.
 *
 * Client components call the same-origin hotel BFF proxy (`/api/hotel/...`),
 * which attaches the HttpOnly access token and the X-Hotel-ID context
 * server-side. No tokens or hotel ids are handled here. Text settings and media
 * are separate calls — saving settings never re-sends images.
 */
import type { ApiError } from "./client";
import type {
  HotelMedia,
  HotelProfile,
  HotelSettings,
  MediaKind,
} from "./types";

const PROXY_BASE = "/api/hotel";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${PROXY_BASE}${path}`, init);

  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
    throw { status: 401, code: "session_expired", message: "" } as ApiError;
  }
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
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function jsonRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

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
