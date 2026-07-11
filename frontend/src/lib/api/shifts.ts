/**
 * Client-side shifts / handover / daily-close API (Phase 12). Calls the
 * same-origin hotel BFF proxy. The backend owns the business date, all
 * drawer math (expected cash), every workflow rule and the day-close lock —
 * these helpers never compute money or dates themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  DailyClose,
  DailyCloseListItem,
  DailyClosePreview,
  DailyCloseStatement,
  HandoverVoucher,
  PaginatedResponse,
  Shift,
  ShiftCashSummary,
  ShiftHandover,
  ShiftHandoverListItem,
  ShiftListItem,
  ShiftStatement,
  ShiftsOverview,
  UnassignedMovements,
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

const B = "/shifts";

export function getShiftsOverview(): Promise<ShiftsOverview> {
  return hotelJson<ShiftsOverview>(`${B}/overview`);
}

export function getCurrentShift(): Promise<{
  shift: Shift | null;
  cash_summary?: ShiftCashSummary;
}> {
  return hotelJson<{ shift: Shift | null; cash_summary?: ShiftCashSummary }>(
    `${B}/current`,
  );
}

// --- Shifts ---------------------------------------------------------------------

export interface ShiftListParams {
  search?: string;
  status?: string;
  business_date?: string;
  responsible_user?: number;
  ordering?: string;
  page?: number;
}

export function listShifts(
  params?: ShiftListParams,
): Promise<PaginatedResponse<ShiftListItem>> {
  return hotelJson<PaginatedResponse<ShiftListItem>>(`${B}${toQuery(params)}`);
}

export function getShift(id: number): Promise<Shift> {
  return hotelJson<Shift>(`${B}/${id}`);
}

export interface ShiftOpenBody {
  opening_cash_amount?: string;
  opening_notes?: string;
  internal_notes?: string;
}

export function openShift(body: ShiftOpenBody): Promise<Shift> {
  return hotelJson<Shift>(`${B}`, { method: "POST", body: JSON.stringify(body) });
}

export function updateShift(
  id: number,
  body: Partial<ShiftOpenBody>,
): Promise<Shift> {
  return hotelJson<Shift>(`${B}/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function closeShift(
  id: number,
  body: { actual_cash_amount: string; difference_reason?: string; closing_notes?: string },
): Promise<Shift> {
  return hotelJson<Shift>(`${B}/${id}/close`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelShift(id: number, reason: string): Promise<Shift> {
  return hotelJson<Shift>(`${B}/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function getShiftSummary(id: number): Promise<{
  shift: ShiftListItem;
  cash_summary: ShiftCashSummary;
  unassigned_movements: UnassignedMovements;
}> {
  return hotelJson(`${B}/${id}/summary`);
}

export function getShiftStatement(id: number): Promise<ShiftStatement> {
  return hotelJson<ShiftStatement>(`${B}/${id}/statement`);
}

// --- Handovers -------------------------------------------------------------------

export interface HandoverListParams {
  search?: string;
  status?: string;
  from_shift?: number;
  to_user?: number;
  date?: string;
  ordering?: string;
  page?: number;
}

export function listHandovers(
  params?: HandoverListParams,
): Promise<PaginatedResponse<ShiftHandoverListItem>> {
  return hotelJson<PaginatedResponse<ShiftHandoverListItem>>(
    `${B}/handovers${toQuery(params)}`,
  );
}

export function getHandover(id: number): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}`);
}

export function getHandoverVoucher(id: number): Promise<HandoverVoucher> {
  return hotelJson<HandoverVoucher>(`${B}/handovers/${id}/voucher`);
}

export interface HandoverBody {
  from_shift: number;
  to_user: number;
  summary_notes?: string;
  pending_tasks_notes?: string;
  cash_notes?: string;
  guest_notes?: string;
  maintenance_notes?: string;
  lost_found_notes?: string;
}

export function createHandover(body: HandoverBody): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateHandover(
  id: number,
  body: Partial<Omit<HandoverBody, "from_shift">>,
): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function submitHandover(id: number): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}/submit`, {
    method: "POST",
    body: "{}",
  });
}

export function acceptHandover(id: number, note = ""): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}/accept`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function rejectHandover(id: number, reason: string): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function cancelHandover(id: number, reason: string): Promise<ShiftHandover> {
  return hotelJson<ShiftHandover>(`${B}/handovers/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// --- Daily close -------------------------------------------------------------------

export interface DailyCloseListParams {
  status?: string;
  business_date?: string;
  ordering?: string;
  page?: number;
}

export function listDailyCloses(
  params?: DailyCloseListParams,
): Promise<PaginatedResponse<DailyCloseListItem>> {
  return hotelJson<PaginatedResponse<DailyCloseListItem>>(
    `${B}/daily-close${toQuery(params)}`,
  );
}

/**
 * Read-only pre-close check. Writes nothing and no longer returns a DailyClose
 * row — it returns the blocking errors, warnings, informational alerts and the
 * preview totals the backend computed for the current business date.
 */
export function prepareDailyClose(
  businessDate?: string,
): Promise<DailyClosePreview> {
  return hotelJson<DailyClosePreview>(`${B}/daily-close/prepare`, {
    method: "POST",
    body: JSON.stringify(businessDate ? { business_date: businessDate } : {}),
  });
}

export function closeBusinessDay(
  businessDate?: string,
  notes = "",
): Promise<DailyClose> {
  return hotelJson<DailyClose>(`${B}/daily-close/close`, {
    method: "POST",
    body: JSON.stringify({ business_date: businessDate || null, notes }),
  });
}

export function getDailyClose(businessDate: string): Promise<DailyClose> {
  return hotelJson<DailyClose>(`${B}/daily-close/${businessDate}`);
}

/** Print-friendly daily-close statement built from the STORED snapshot. */
export function getDailyCloseStatement(pk: number): Promise<DailyCloseStatement> {
  return hotelJson<DailyCloseStatement>(`${B}/daily-close/${pk}/statement`);
}
