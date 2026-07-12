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
  HotelNotification,
  HotelSubscription,
  HotelSubscriptionState,
  PaginatedResponse,
  PlatformDashboard,
  PlatformOverview,
  PlatformPayment,
  PlatformPaymentMethod,
  PlatformPublicSettings,
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

// --- Dashboard (Phase 16) -----------------------------------------------------

export function fetchDashboard(): Promise<PlatformDashboard> {
  return request<PlatformDashboard>("/dashboard");
}

// --- Hotels -----------------------------------------------------------------

export interface HotelListParams {
  status?: string;
  subscription?: string;
  public?: string;
  city?: string;
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
  body: Partial<Pick<Hotel, "name" | "slug">>,
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

// --- Hotel status lifecycle (Phase 16) ----------------------------------------

export function activateHotel(id: number): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}/activate`, { method: "POST" });
}

export function suspendHotel(id: number, reason: string): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}/suspend`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function unsuspendHotel(id: number): Promise<Hotel> {
  return request<Hotel>(`/hotels/${id}/unsuspend`, { method: "POST" });
}

// --- Subscription lifecycle per hotel (Phase 16) -------------------------------

export interface ManualPaymentInput {
  payment_amount?: string;
  payment_method?: PlatformPaymentMethod;
  payment_reference?: string;
}

export function startTrial(
  hotelId: number,
  body: { plan: number; trial_days?: number; notes?: string },
): Promise<HotelSubscription> {
  return request<HotelSubscription>(`/hotels/${hotelId}/subscriptions/start-trial`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function activatePaid(
  hotelId: number,
  body: { plan: number; starts_at?: string; ends_at?: string; notes?: string } &
    ManualPaymentInput,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(
    `/hotels/${hotelId}/subscriptions/activate-paid`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function renewSubscription(
  hotelId: number,
  body: { ends_at?: string; days?: number; notes?: string } & ManualPaymentInput,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(`/hotels/${hotelId}/subscriptions/renew`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface ChangePlanBody extends ManualPaymentInput {
  plan: number;
  reason?: string;
  notes?: string;
}

/** Switch a LIVE subscription to a different plan (optionally recording a
 * manual payment). Used only when there is an active/trial subscription. */
export function changePlan(
  hotelId: number,
  body: ChangePlanBody,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(
    `/hotels/${hotelId}/subscriptions/change-plan`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export interface ReactivateBody extends ManualPaymentInput {
  plan: number;
  starts_at?: string;
  ends_at?: string;
  notes?: string;
}

/** Reactivate a hotel whose subscription has ENDED (no live sub, history
 * exists). Returns the new subscription (201). */
export function reactivateSubscription(
  hotelId: number,
  body: ReactivateBody,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(
    `/hotels/${hotelId}/subscriptions/reactivate`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** Rich subscription state for one hotel (same shape as the hotel profile's
 * `subscription_state`): effective status, snapshot terms, entitlements. */
export function getSubscriptionState(
  hotelId: number,
): Promise<HotelSubscriptionState> {
  return request<HotelSubscriptionState>(
    `/hotels/${hotelId}/subscriptions/state`,
  );
}

export function cancelHotelSubscription(
  hotelId: number,
  notes?: string,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(`/hotels/${hotelId}/subscriptions/cancel`, {
    method: "POST",
    body: JSON.stringify({ notes: notes ?? "" }),
  });
}

export function expireHotelSubscription(
  hotelId: number,
): Promise<HotelSubscription> {
  return request<HotelSubscription>(`/hotels/${hotelId}/subscriptions/expire`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function fetchSubscriptionHistory(
  hotelId: number,
): Promise<HotelSubscription[]> {
  return request<HotelSubscription[]>(`/hotels/${hotelId}/subscriptions/history`);
}

// --- Manual platform payments (Phase 16 — never a gateway) ---------------------

export function listPlatformPayments(
  hotelId?: number,
): Promise<PlatformPayment[]> {
  return request<PlatformPayment[]>(
    `/subscription-payments${hotelId ? `?hotel=${hotelId}` : ""}`,
  );
}

export function voidPlatformPayment(
  id: number,
  reason: string,
): Promise<PlatformPayment> {
  return request<PlatformPayment>(`/subscription-payments/${id}/void`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// --- Plan activation (Phase 16) -------------------------------------------------

export function activatePlan(id: number): Promise<SubscriptionPlan> {
  return request<SubscriptionPlan>(`/plans/${id}/activate`, { method: "POST" });
}

export function deactivatePlan(id: number): Promise<SubscriptionPlan> {
  return request<SubscriptionPlan>(`/plans/${id}/deactivate`, { method: "POST" });
}

// --- Public site settings (Phase 16) --------------------------------------------

export function getPublicSiteSettings(): Promise<PlatformPublicSettings> {
  return request<PlatformPublicSettings>("/public-site-settings");
}

export function updatePublicSiteSettings(
  body: Partial<PlatformPublicSettings>,
): Promise<PlatformPublicSettings> {
  return request<PlatformPublicSettings>("/public-site-settings", {
    method: "PATCH",
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
    | "price_yearly"
    | "currency"
    | "billing_cycle"
    | "trial_days"
    | "room_limit"
    | "user_limit"
    | "max_public_bookings_per_month"
    | "feature_codes"
    | "is_active"
    | "is_public"
    | "sort_order"
    | "notes"
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
  expiring?: "soon";
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

// --- Platform-owner notification centre (notifications closure) --------------

export interface PlatformNotificationsOverview {
  unread_count: number;
  warning_count: number;
  danger_count: number;
  archived_count: number;
}

export interface PlatformNotificationListParams {
  unread?: string;
  archived?: string;
  category?: string;
  severity?: string;
  page?: number;
}

export function getPlatformNotificationsOverview(): Promise<PlatformNotificationsOverview> {
  return request<PlatformNotificationsOverview>("/notifications/overview");
}

export function getPlatformUnreadCount(): Promise<{ unread: number }> {
  return request<{ unread: number }>("/notifications/unread-count");
}

export function listPlatformNotifications(
  params?: PlatformNotificationListParams,
): Promise<PaginatedResponse<HotelNotification>> {
  return request<PaginatedResponse<HotelNotification>>(
    `/notifications${toQuery(params)}`,
  );
}

export function markPlatformNotificationRead(
  id: number,
): Promise<HotelNotification> {
  return request<HotelNotification>(`/notifications/${id}/mark-read`, {
    method: "POST",
    body: "{}",
  });
}

export function markAllPlatformNotificationsRead(): Promise<{ updated: number }> {
  return request<{ updated: number }>("/notifications/mark-all-read", {
    method: "POST",
    body: "{}",
  });
}

export function archivePlatformNotification(
  id: number,
): Promise<HotelNotification> {
  return request<HotelNotification>(`/notifications/${id}/archive`, {
    method: "POST",
    body: "{}",
  });
}
