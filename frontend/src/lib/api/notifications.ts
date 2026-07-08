/**
 * Client-side notifications + activity API (Phase 14). Calls the same-origin
 * hotel BFF proxy. In-app only — no external channels exist. The backend
 * creates every event/notification through its central service; the client
 * only reads and flips the recipient's own read/archive state.
 */
import { hotelJson } from "./hotelFetch";
import type {
  ActivityEventRow,
  HotelNotification,
  NotificationsOverview,
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

const B = "/notifications";

export function getNotificationsOverview(): Promise<NotificationsOverview> {
  return hotelJson<NotificationsOverview>(`${B}/overview`);
}

export function getUnreadCount(): Promise<{ unread: number }> {
  return hotelJson<{ unread: number }>(`${B}/unread-count`);
}

export interface NotificationListParams {
  unread?: string;
  archived?: string;
  category?: string;
  severity?: string;
  date?: string;
  page?: number;
}

export function listNotifications(
  params?: NotificationListParams,
): Promise<PaginatedResponse<HotelNotification>> {
  return hotelJson<PaginatedResponse<HotelNotification>>(`${B}${toQuery(params)}`);
}

export function markNotificationRead(id: number): Promise<HotelNotification> {
  return hotelJson<HotelNotification>(`${B}/${id}/mark-read`, {
    method: "POST",
    body: "{}",
  });
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return hotelJson<{ updated: number }>(`${B}/mark-all-read`, {
    method: "POST",
    body: "{}",
  });
}

export function archiveNotification(id: number): Promise<HotelNotification> {
  return hotelJson<HotelNotification>(`${B}/${id}/archive`, {
    method: "POST",
    body: "{}",
  });
}

export interface ActivityListParams {
  category?: string;
  severity?: string;
  event_type?: string;
  actor?: number;
  date?: string;
  page?: number;
}

export function listActivity(
  params?: ActivityListParams,
): Promise<PaginatedResponse<ActivityEventRow>> {
  return hotelJson<PaginatedResponse<ActivityEventRow>>(
    `${B}/activity${toQuery(params)}`,
  );
}
