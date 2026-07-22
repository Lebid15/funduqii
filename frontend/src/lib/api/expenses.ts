/**
 * Client-side API for the standalone Expenses section (EXPENSES-CLOSURE).
 *
 * Calls the same-origin hotel BFF proxy. The backend routes still live under
 * `/finance/*` (the API was not moved, only the frontend page) — the backend is
 * the source of truth for all money math, FX derivation, idempotency, and
 * lifecycle rules; these helpers never compute a base amount themselves.
 */
import type { ApiError } from "./client";
import { hotelFetch, hotelJson } from "./hotelFetch";
import type { Expense, ExpenseType, PaginatedResponse } from "./types";

const PROXY_BASE = "/api/hotel";

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

const B = "/finance";

/** A fresh idempotency key per money-moving attempt, REUSED across retries of
 * the same attempt (a new key only after a success). */
export function mintIdempotencyKey(): string {
  return crypto.randomUUID();
}

// --- Form metadata ----------------------------------------------------------

/** Base + accepted currencies for the entry form. Gated on `expenses.view` so
 * an expenses clerk does NOT need the separate `settings.view` permission to
 * record a foreign-currency expense. */
export function getExpenseMeta(): Promise<{
  base_currency: string;
  accepted_currencies: string[];
}> {
  return hotelJson<{ base_currency: string; accepted_currencies: string[] }>(
    `${B}/expenses/meta`,
  );
}

// --- Expense types (manageable per-hotel categories) ------------------------

/** List types. `all: true` (management tab) needs `expenses.manage_types` and
 * includes inactive types; otherwise only ACTIVE types (create-form dropdown). */
export function listExpenseTypes(params?: { all?: boolean }): Promise<ExpenseType[]> {
  const q = params?.all ? "?all=1" : "";
  return hotelJson<ExpenseType[]>(`${B}/expense-types${q}`);
}

export function createExpenseType(name: string): Promise<ExpenseType> {
  return hotelJson<ExpenseType>(`${B}/expense-types`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateExpenseType(
  id: number,
  body: { name?: string; is_active?: boolean },
): Promise<ExpenseType> {
  return hotelJson<ExpenseType>(`${B}/expense-types/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// --- Expenses ---------------------------------------------------------------

export interface ExpenseListParams {
  status?: string;
  expense_type?: number;
  method?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
}

export function listExpenses(
  params?: ExpenseListParams,
): Promise<PaginatedResponse<Expense>> {
  return hotelJson<PaginatedResponse<Expense>>(`${B}/expenses${toQuery(params)}`);
}

/** CREATE payload. For a base-currency expense send `amount`. For a foreign
 * one send `currency` + `original_amount` + `exchange_rate` (the server derives
 * the base `amount`). `idempotency_key` makes a double-submit safe. */
export interface ExpenseCreateBody {
  expense_type: number;
  description: string;
  method: string;
  amount?: string;
  currency?: string;
  original_amount?: string;
  exchange_rate?: string;
  rate_basis?: string;
  notes?: string;
  idempotency_key?: string;
}

/** Atomic financial edit — any subset (money fields re-derive the base). */
export interface ExpenseUpdateBody {
  description?: string;
  notes?: string;
  method?: string;
  expense_type?: number;
  amount?: string;
  currency?: string;
  original_amount?: string;
  exchange_rate?: string;
  rate_basis?: string;
}

export function createExpense(body: ExpenseCreateBody): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateExpense(id: number, body: ExpenseUpdateBody): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Void (before day close). Returns a minimal ack, not the full voucher. */
export interface ExpenseVoidAck {
  id: number;
  expense_number: string;
  status: string;
  voided_at: string | null;
}

export function voidExpense(id: number, reason: string): Promise<ExpenseVoidAck> {
  return hotelJson<ExpenseVoidAck>(`${B}/expenses/${id}/void`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Corrective movement (after day close) — a distinct linked counter-voucher. */
export function reverseExpense(id: number, reason: string): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses/${id}/reverse`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function getExpenseVoucher(
  id: number,
): Promise<{ document: string; hotel: import("./types").HotelHeader; expense: Expense }> {
  return hotelJson(`${B}/expenses/${id}/voucher`);
}

// --- Attachment (one optional private receipt) ------------------------------

/** Upload/replace the receipt (multipart; no Content-Type header — the browser
 * sets the boundary). Field name `file`. */
export function uploadExpenseAttachment(
  id: number,
  file: File,
): Promise<{ id: number; has_attachment: boolean }> {
  const form = new FormData();
  form.append("file", file);
  return hotelFetch<{ id: number; has_attachment: boolean }>(
    `${B}/expenses/${id}/attachment`,
    { method: "POST", body: form },
  );
}

export function deleteExpenseAttachment(
  id: number,
): Promise<{ id: number; has_attachment: boolean }> {
  return hotelJson<{ id: number; has_attachment: boolean }>(
    `${B}/expenses/${id}/attachment`,
    { method: "DELETE" },
  );
}

/** Mint a short-lived signed URL for the private attachment (secondary path;
 * e.g. external embedding). For in-app viewing prefer the blob helper below. */
export function getExpenseAttachmentUrl(
  id: number,
): Promise<{ url: string; expires_in: number }> {
  return hotelJson<{ url: string; expires_in: number }>(
    `${B}/expenses/${id}/attachment/url`,
  );
}

/**
 * PRIMARY viewing path: fetch the attachment bytes THROUGH the authenticated
 * BFF proxy (session-gated by `expenses.view`; the proxy streams binary
 * untouched) and return an object URL for an `<img>`/PDF viewer. The CALLER owns
 * the URL and MUST call `URL.revokeObjectURL` when done. Mirrors the shipped
 * reservation-document viewer (a private file is never a public URL).
 */
export async function getExpenseAttachmentBlobUrl(id: number): Promise<string> {
  const response = await fetch(`${PROXY_BASE}${B}/expenses/${id}/attachment/file`);
  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
    throw { status: 401, code: "session_expired", message: "" } as ApiError;
  }
  if (!response.ok) {
    throw {
      status: response.status,
      code: "error",
      message: response.statusText,
    } as ApiError;
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
