/**
 * Client-side operations API (Phase 10): housekeeping tasks, maintenance
 * requests and lost & found. Calls the same-origin hotel BFF proxy. The
 * backend owns numbering, every status workflow and all room-status safety
 * rules — these helpers never change a room status themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  ArrivalNotReadyRow,
  HousekeepingServiceOutcome,
  HousekeepingTask,
  HousekeepingTaskListItem,
  LostFoundClaimProofType,
  LostFoundItem,
  LostFoundItemListItem,
  LostReport,
  LostReportListItem,
  MaintenanceRequest,
  MaintenanceRequestListItem,
  OperationsOverview,
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

const B = "/operations";

export function getOperationsOverview(): Promise<OperationsOverview> {
  return hotelJson<OperationsOverview>(`${B}/overview`);
}

// --- Housekeeping -------------------------------------------------------------

export interface HousekeepingListParams {
  search?: string;
  status?: string;
  task_type?: string;
  priority?: string;
  room?: number;
  assigned_to?: number;
  /** "true" limits the list to tasks assigned to the current user. */
  mine?: "true";
  date?: string;
  ordering?: string;
  page?: number;
}

export function listHousekeepingTasks(
  params?: HousekeepingListParams,
): Promise<PaginatedResponse<HousekeepingTaskListItem>> {
  return hotelJson<PaginatedResponse<HousekeepingTaskListItem>>(
    `${B}/housekeeping${toQuery(params)}`,
  );
}

export function getHousekeepingTask(id: number): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}`);
}

export interface HousekeepingCreateBody {
  room: number;
  stay?: number | null;
  task_type?: string;
  priority?: string;
  assigned_to?: number | null;
  notes?: string;
  internal_notes?: string;
}

export function createHousekeepingTask(
  body: HousekeepingCreateBody,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateHousekeepingTask(
  id: number,
  body: Partial<Omit<HousekeepingCreateBody, "room" | "stay" | "assigned_to">>,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setHousekeepingStatus(
  id: number,
  status: string,
  note = "",
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export function assignHousekeepingTask(
  id: number,
  assignedTo: number | null,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/assign`, {
    method: "POST",
    body: JSON.stringify({ assigned_to: assignedTo }),
  });
}

export function completeHousekeepingTask(
  id: number,
  markRoomAvailable: boolean,
  note = "",
  /** The terminal service result. Omitted => the backend defaults to
   * "cleaned". `come_back_later` is NOT a valid outcome here — use
   * `comeBackLaterHousekeepingTask` (a separate non-terminal action). */
  serviceOutcome?: HousekeepingServiceOutcome,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/complete`, {
    method: "POST",
    body: JSON.stringify({
      mark_room_available: markRoomAvailable,
      note,
      ...(serviceOutcome ? { service_outcome: serviceOutcome } : {}),
    }),
  });
}

/** Non-terminal "come back later" defer — the task STAYS active (no status /
 * outcome change), only an optional note is recorded. Separate from
 * completion on purpose. */
export function comeBackLaterHousekeepingTask(
  id: number,
  body: { note?: string } = {},
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/come-back-later`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelHousekeepingTask(
  id: number,
  reason: string,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function approveInspection(id: number, note = ""): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/inspect/approve`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function rejectInspection(
  id: number,
  reason: string,
): Promise<HousekeepingTask> {
  return hotelJson<HousekeepingTask>(`${B}/housekeeping/${id}/inspect/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Rooms with a confirmed arrival today that are not ready yet (plain array). */
export function listArrivalsNotReady(): Promise<ArrivalNotReadyRow[]> {
  return hotelJson<ArrivalNotReadyRow[]>(`${B}/housekeeping/arrivals-not-ready`);
}

// --- Maintenance ----------------------------------------------------------------

export interface MaintenanceListParams {
  search?: string;
  status?: string;
  category?: string;
  priority?: string;
  room?: number;
  assigned_to?: number;
  affects_room_availability?: string;
  ordering?: string;
  page?: number;
}

export function listMaintenanceRequests(
  params?: MaintenanceListParams,
): Promise<PaginatedResponse<MaintenanceRequestListItem>> {
  return hotelJson<PaginatedResponse<MaintenanceRequestListItem>>(
    `${B}/maintenance${toQuery(params)}`,
  );
}

export function getMaintenanceRequest(id: number): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}`);
}

export interface MaintenanceCreateBody {
  room?: number | null;
  stay?: number | null;
  title: string;
  description?: string;
  category?: string;
  priority?: string;
  affects_room_availability?: boolean;
  room_block_status?: string;
  assigned_to?: number | null;
  internal_notes?: string;
}

export function createMaintenanceRequest(
  body: MaintenanceCreateBody,
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateMaintenanceRequest(
  id: number,
  body: Partial<Omit<MaintenanceCreateBody, "room" | "stay" | "assigned_to">>,
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setMaintenanceStatus(
  id: number,
  status: string,
  note = "",
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export function assignMaintenanceRequest(
  id: number,
  assignedTo: number | null,
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}/assign`, {
    method: "POST",
    body: JSON.stringify({ assigned_to: assignedTo }),
  });
}

export function resolveMaintenanceRequest(
  id: number,
  resolutionNotes = "",
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution_notes: resolutionNotes }),
  });
}

export type RoomNextStatus = "keep" | "dirty" | "available";

export function closeMaintenanceRequest(
  id: number,
  roomNextStatus: RoomNextStatus,
  note = "",
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}/close`, {
    method: "POST",
    body: JSON.stringify({ room_next_status: roomNextStatus, note }),
  });
}

export function cancelMaintenanceRequest(
  id: number,
  reason: string,
): Promise<MaintenanceRequest> {
  return hotelJson<MaintenanceRequest>(`${B}/maintenance/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// --- Lost & Found -----------------------------------------------------------------

export interface LostFoundListParams {
  search?: string;
  status?: string;
  category?: string;
  room?: number;
  guest?: number;
  date?: string;
  ordering?: string;
  page?: number;
}

export function listLostFoundItems(
  params?: LostFoundListParams,
): Promise<PaginatedResponse<LostFoundItemListItem>> {
  return hotelJson<PaginatedResponse<LostFoundItemListItem>>(
    `${B}/lost-found${toQuery(params)}`,
  );
}

export function getLostFoundItem(id: number): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}`);
}

export interface LostFoundCreateBody {
  title: string;
  description?: string;
  category?: string;
  status?: "found" | "stored";
  found_at?: string | null;
  found_location?: string;
  room?: number | null;
  stay?: number | null;
  guest?: number | null;
  stored_location?: string;
  notes?: string;
  internal_notes?: string;
}

export function createLostFoundItem(
  body: LostFoundCreateBody,
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateLostFoundItem(
  id: number,
  body: Partial<Omit<LostFoundCreateBody, "status" | "found_at">>,
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setLostFoundStatus(
  id: number,
  status: string,
  note = "",
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export interface ClaimBody {
  claimed_by_name?: string;
  claimed_by_phone?: string;
  note?: string;
  /** WP7 ownership proof. REQUIRED by the backend for SENSITIVE categories
   * (money / jewelry / documents) — omitting it there is rejected with
   * `claim_proof_required` (422). Optional for non-sensitive items. */
  claim_proof_type?: LostFoundClaimProofType;
  claim_proof_reference?: string;
}

export function claimLostFoundItem(
  id: number,
  body: ClaimBody,
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}/claim`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function returnLostFoundItem(
  id: number,
  body: ClaimBody,
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}/return`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function disposeLostFoundItem(
  id: number,
  reason: string,
): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}/dispose`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function closeLostFoundItem(id: number, note = ""): Promise<LostFoundItem> {
  return hotelJson<LostFoundItem>(`${B}/lost-found/${id}/close`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

// --- Lost reports (the "a guest reports a lost item" cycle + safe matching) -------

export interface LostReportListParams {
  status?: string;
  category?: string;
  guest?: number;
  stay?: number;
  date?: string;
  search?: string;
  ordering?: string;
  page?: number;
}

export function listLostReports(
  params?: LostReportListParams,
): Promise<PaginatedResponse<LostReportListItem>> {
  return hotelJson<PaginatedResponse<LostReportListItem>>(
    `${B}/lost-reports${toQuery(params)}`,
  );
}

export function getLostReport(id: number): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}`);
}

export interface LostReportCreateBody {
  category?: string;
  description?: string;
  distinctive_marks?: string;
  last_seen_location?: string;
  lost_at?: string | null;
  /** REQUIRED — a blank value is rejected by the backend with 422
   * `claimant_required`. */
  reporter_name: string;
  reporter_phone?: string;
  guest?: number | null;
  stay?: number | null;
  reservation?: number | null;
  internal_notes?: string;
}

export function createLostReport(body: LostReportCreateBody): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type LostReportUpdateBody = Partial<LostReportCreateBody>;

export function updateLostReport(
  id: number,
  body: LostReportUpdateBody,
): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Advance a report's status. The backend permits ONLY open→searching here. */
export function setLostReportStatus(
  id: number,
  status: string,
  note = "",
): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export function matchLostReport(id: number, foundItem: number): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/match`, {
    method: "POST",
    body: JSON.stringify({ found_item: foundItem }),
  });
}

export function unmatchLostReport(id: number, reason: string): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/unmatch`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export interface LostReportHandoverBody {
  recipient_name?: string;
  recipient_phone?: string;
  note?: string;
  /** WP7 ownership proof — enforced by the backend ONLY for sensitive matched
   * items; omitting it there is rejected with `claim_proof_required` (422). */
  claim_proof_type?: LostFoundClaimProofType;
  claim_proof_reference?: string;
}

export function handoverLostReport(
  id: number,
  body: LostReportHandoverBody,
): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/handover`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function closeUnfoundLostReport(
  id: number,
  reason: string,
): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/close-unfound`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function cancelLostReport(id: number, reason: string): Promise<LostReport> {
  return hotelJson<LostReport>(`${B}/lost-reports/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export interface LostReportCandidateParams {
  search?: string;
  category?: string;
}

/** Found items eligible to match this report (PLAIN array, capped 100). */
export function listLostReportCandidates(
  id: number,
  params?: LostReportCandidateParams,
): Promise<LostFoundItemListItem[]> {
  return hotelJson<LostFoundItemListItem[]>(
    `${B}/lost-reports/${id}/candidates${toQuery(params)}`,
  );
}
