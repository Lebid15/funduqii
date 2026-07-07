/**
 * Shared client-side fetch for the hotel BFF proxy (`/api/hotel/...`).
 *
 * The proxy attaches the HttpOnly access token + X-Hotel-ID context server-side;
 * nothing sensitive is handled here. A 401 sends the user back to /login.
 */
import type { ApiError } from "./client";

const PROXY_BASE = "/api/hotel";

export async function hotelFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
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

export function hotelJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  return hotelFetch<T>(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}
