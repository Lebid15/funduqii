/**
 * Client-side platform API.
 *
 * Client components call the same-origin BFF proxy (`/api/platform/...`), which
 * attaches the HttpOnly access token server-side. No tokens are handled here.
 * A 401 (`session_expired`) sends the user back to /login.
 */
import type { ApiError } from "./client";
import type {
  Hotel,
  HotelSubscription,
  PaginatedResponse,
  PlatformOverview,
  PlatformSettings,
  SubscriptionPlan,
} from "./types";

const PROXY_BASE = "/api/platform";

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${PROXY_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
    // Reject for any caller awaiting; the navigation supersedes it.
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

// --- Overview ---------------------------------------------------------------

export function fetchOverview(): Promise<PlatformOverview> {
  return request<PlatformOverview>("/overview");
}

// --- Hotels -----------------------------------------------------------------

export interface HotelListParams {
  status?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export function listHotels(
  params?: HotelListParams,
): Promise<PaginatedResponse<Hotel>> {
  return request<PaginatedResponse<Hotel>>(`/hotels${toQuery(params)}`);
}

export function getHotel(id: number): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}`);
}

export interface HotelCreateBody {
  name: string;
  slug: string;
  status?: string;
  manager?: { email: string; full_name: string; password: string };
}

export function createHotel(body: HotelCreateBody): Promise<Hotel> {
  return request<Hotel>("/hotels", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateHotel(
  id: number,
  body: Partial<Pick<Hotel, "name" | "slug" | "status">>,
): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setHotelManager(
  id: number,
  body: { email: string; full_name: string; password: string },
): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}/manager`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Plans ------------------------------------------------------------------

export interface PlanListParams {
  is_active?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export function listPlans(
  params?: PlanListParams,
): Promise<PaginatedResponse<SubscriptionPlan>> {
  return request<PaginatedResponse<SubscriptionPlan>>(
    `/plans${toQuery(params)}`,
  );
}

export type PlanWriteBody = Partial<
  Pick<
    SubscriptionPlan,
    | "name"
    | "slug"
    | "description"
    | "price"
    | "currency"
    | "billing_cycle"
    | "trial_days"
    | "room_limit"
    | "user_limit"
    | "feature_codes"
    | "is_active"
    | "sort_order"
  >
>;

export function createPlan(body: PlanWriteBody): Promise<SubscriptionPlan> {
  return request<SubscriptionPlan>("/plans", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updatePlan(
  id: number,
  body: PlanWriteBody,
): Promise<SubscriptionPlan> {
  return request<SubscriptionPlan>(`/plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deletePlan(id: number): Promise<void> {
  return request<void>(`/plans/${id}`, { method: "DELETE" });
}

// --- Subscriptions ----------------------------------------------------------

export interface SubscriptionListParams {
  status?: string;
  hotel?: number;
  page?: number;
}

export function listSubscriptions(
  params?: SubscriptionListParams,
): Promise<PaginatedResponse<HotelSubscription>> {
  return request<PaginatedResponse<HotelSubscription>>(
    `/subscriptions${toQuery(params)}`,
  );
}

export interface SubscriptionCreateBody {
  hotel: number;
  plan: number;
  kind: "trial" | "paid";
  trial_days?: number;
  notes?: string;
}

export function createSubscription(
  body: SubscriptionCreateBody,
): Promise<HotelSubscription> {
  return request<HotelSubscription>("/subscriptions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSubscription(
  id: number,
  body: { status?: "cancelled" | "expired"; notes?: string },
): Promise<HotelSubscription> {
  return request<HotelSubscription>(`/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- Settings ---------------------------------------------------------------

export function getSettings(): Promise<PlatformSettings> {
  return request<PlatformSettings>("/settings");
}

export function updateSettings(
  body: Partial<PlatformSettings>,
): Promise<PlatformSettings> {
  return request<PlatformSettings>("/settings", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
