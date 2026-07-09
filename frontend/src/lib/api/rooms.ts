/**
 * Client-side floors / room types / rooms API (Phase 5).
 *
 * Calls the same-origin hotel BFF proxy (`/api/hotel/...`); the proxy attaches
 * auth + hotel context server-side. Nothing sensitive is handled here.
 */
import { hotelJson } from "./hotelFetch";
import type {
  Floor,
  PaginatedResponse,
  Room,
  RoomOperationalBoard,
  RoomStatus,
  RoomType,
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

// --- Floors -----------------------------------------------------------------

export function listFloors(): Promise<PaginatedResponse<Floor>> {
  return hotelJson<PaginatedResponse<Floor>>("/floors?page_size=100");
}

export type FloorWriteBody = Partial<
  Pick<Floor, "name" | "number" | "description" | "sort_order" | "is_active">
>;

export function createFloor(body: FloorWriteBody): Promise<Floor> {
  return hotelJson<Floor>("/floors", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateFloor(id: number, body: FloorWriteBody): Promise<Floor> {
  return hotelJson<Floor>(`/floors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteFloor(id: number): Promise<void> {
  return hotelJson<void>(`/floors/${id}`, { method: "DELETE" });
}

// --- Room types -------------------------------------------------------------

export function listRoomTypes(): Promise<PaginatedResponse<RoomType>> {
  return hotelJson<PaginatedResponse<RoomType>>("/room-types?page_size=100");
}

export type RoomTypeWriteBody = Partial<
  Pick<
    RoomType,
    | "name"
    | "code"
    | "description"
    | "base_capacity"
    | "max_capacity"
    | "bed_type"
    | "amenities"
    | "base_rate"
    | "is_active"
    | "sort_order"
    | "public_is_visible"
    | "public_name"
    | "public_description"
    | "public_base_price"
    | "public_sort_order"
  >
>;

export function createRoomType(body: RoomTypeWriteBody): Promise<RoomType> {
  return hotelJson<RoomType>("/room-types", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateRoomType(
  id: number,
  body: RoomTypeWriteBody,
): Promise<RoomType> {
  return hotelJson<RoomType>(`/room-types/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRoomType(id: number): Promise<void> {
  return hotelJson<void>(`/room-types/${id}`, { method: "DELETE" });
}

// --- Rooms ------------------------------------------------------------------

export interface RoomListParams {
  floor?: number;
  room_type?: number;
  status?: string;
  search?: string;
  include_archived?: string;
  page?: number;
  page_size?: number;
}

export function listRooms(
  params?: RoomListParams,
): Promise<PaginatedResponse<Room>> {
  return hotelJson<PaginatedResponse<Room>>(`/rooms${toQuery(params)}`);
}

export interface RoomWriteBody {
  number: string;
  display_name?: string;
  floor: number;
  room_type: number;
  is_active?: boolean;
}

export function createRoom(body: RoomWriteBody): Promise<Room> {
  return hotelJson<Room>("/rooms", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateRoom(
  id: number,
  body: Partial<RoomWriteBody>,
): Promise<Room> {
  return hotelJson<Room>(`/rooms/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRoom(id: number): Promise<void> {
  return hotelJson<void>(`/rooms/${id}`, { method: "DELETE" });
}

/** READ-ONLY operational board: every room with its computed display status,
 * current stay and next reservation, plus hotel/floor summaries — one call. */
export function getOperationalBoard(): Promise<RoomOperationalBoard> {
  return hotelJson<RoomOperationalBoard>("/rooms/operational-board");
}

export function changeRoomStatus(
  id: number,
  status: RoomStatus,
  note?: string,
): Promise<Room> {
  return hotelJson<Room>(`/rooms/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note: note ?? "" }),
  });
}
