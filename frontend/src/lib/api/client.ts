/**
 * Unified API client for the Funduqii frontend.
 *
 * Phase 2: the client can attach an access token (`Authorization: Bearer …`)
 * and the tenant-context header (`X-Hotel-ID`) in an extensible way. It does
 * NOT store tokens or any operational data (no localStorage as a source of
 * truth) — callers pass credentials per request. Auth screens are not built
 * yet; this is the transport layer only.
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

/** Matches the backend's unified error envelope. */
export interface ApiError {
  status: number;
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiRequestOptions extends RequestInit {
  /** Bearer access token to send in the Authorization header. */
  token?: string | null;
  /** Hotel id to scope the request via the X-Hotel-ID header. */
  hotelId?: string | number | null;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

function buildHeaders(
  token: string | null | undefined,
  hotelId: string | number | null | undefined,
  base: HeadersInit | undefined,
): Headers {
  const headers = new Headers(base);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (hotelId !== undefined && hotelId !== null && hotelId !== "") {
    headers.set("X-Hotel-ID", String(hotelId));
  }
  return headers;
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { token, hotelId, headers, ...init } = options;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: buildHeaders(token, hotelId, headers),
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      // The error response had no JSON body.
    }
    const record =
      body && typeof body === "object" ? (body as Record<string, unknown>) : {};
    const error: ApiError = {
      status: response.status,
      code: typeof record.code === "string" ? record.code : "error",
      message:
        typeof record.message === "string" ? record.message : response.statusText,
      details: record.details,
    };
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
