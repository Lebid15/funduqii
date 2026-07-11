/**
 * Client-side internal-finance API (Phase 8). Calls the same-origin hotel BFF
 * proxy. The backend is the source of truth for all money math, numbering, and
 * lifecycle rules — these helpers never compute balances or process payments.
 */
import { hotelJson } from "./hotelFetch";
import type {
  Expense,
  FinanceOverview,
  Folio,
  FolioListItem,
  FolioStatement,
  Invoice,
  PaginatedResponse,
  Payment,
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

const B = "/finance";

export function getFinanceOverview(): Promise<FinanceOverview> {
  return hotelJson<FinanceOverview>(`${B}/overview`);
}

// --- Folios -----------------------------------------------------------------

export interface FolioListParams {
  status?: string;
  reservation?: number;
  stay?: number;
  search?: string;
  page?: number;
}

export function listFolios(params?: FolioListParams): Promise<PaginatedResponse<FolioListItem>> {
  return hotelJson<PaginatedResponse<FolioListItem>>(`${B}/folios${toQuery(params)}`);
}

export function getFolio(id: number): Promise<Folio> {
  return hotelJson<Folio>(`${B}/folios/${id}`);
}

export interface FolioCreateBody {
  reservation?: number | null;
  stay?: number | null;
  guest?: number | null;
  customer_name?: string;
  notes?: string;
}

export function createFolio(body: FolioCreateBody): Promise<Folio> {
  return hotelJson<Folio>(`${B}/folios`, { method: "POST", body: JSON.stringify(body) });
}

export function closeFolio(id: number): Promise<Folio> {
  return hotelJson<Folio>(`${B}/folios/${id}/close`, { method: "POST", body: "{}" });
}

export function voidFolio(id: number, reason: string): Promise<Folio> {
  return hotelJson<Folio>(`${B}/folios/${id}/void`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function getFolioStatement(id: number): Promise<FolioStatement> {
  return hotelJson<FolioStatement>(`${B}/folios/${id}/statement`);
}

// --- Charges ----------------------------------------------------------------

export interface ChargeBody {
  type: string;
  description: string;
  quantity: string;
  unit_amount: string;
  tax_rate?: string;
}

export function addCharge(folioId: number, body: ChargeBody): Promise<Folio> {
  return hotelJson<Folio>(`${B}/folios/${folioId}/charges`, { method: "POST", body: JSON.stringify(body) });
}

export function voidCharge(id: number, reason: string): Promise<Folio> {
  return hotelJson<Folio>(`${B}/charges/${id}/void`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function adjustCharge(id: number, reason: string): Promise<Folio> {
  return hotelJson<Folio>(`${B}/charges/${id}/adjust`, { method: "POST", body: JSON.stringify({ reason }) });
}

// --- Payments ---------------------------------------------------------------

export interface PaymentBody {
  amount: string;
  method: string;
  payer_name?: string;
  reference?: string;
  notes?: string;
}

export function recordPayment(folioId: number, body: PaymentBody): Promise<{ folio: Folio; payment: Payment }> {
  return hotelJson<{ folio: Folio; payment: Payment }>(`${B}/folios/${folioId}/payments`, { method: "POST", body: JSON.stringify(body) });
}

export interface PaymentListParams {
  status?: string;
  method?: string;
  folio?: number;
  date_from?: string;
  date_to?: string;
  page?: number;
}

export function listPayments(params?: PaymentListParams): Promise<PaginatedResponse<Payment>> {
  return hotelJson<PaginatedResponse<Payment>>(`${B}/payments${toQuery(params)}`);
}

export function voidPayment(id: number, reason: string): Promise<Payment> {
  return hotelJson<Payment>(`${B}/payments/${id}/void`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function reversePayment(id: number, reason: string): Promise<{ folio: Folio; payment: Payment }> {
  return hotelJson<{ folio: Folio; payment: Payment }>(`${B}/payments/${id}/reverse`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function getReceipt(id: number): Promise<{ document: string; hotel: import("./types").HotelHeader; payment: Payment }> {
  return hotelJson(`${B}/payments/${id}/receipt`);
}

// --- Invoices ---------------------------------------------------------------

export interface InvoiceListParams {
  status?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
}

export function listInvoices(params?: InvoiceListParams): Promise<PaginatedResponse<Invoice>> {
  return hotelJson<PaginatedResponse<Invoice>>(`${B}/invoices${toQuery(params)}`);
}

export function getInvoice(id: number): Promise<Invoice> {
  return hotelJson<Invoice>(`${B}/invoices/${id}`);
}

export interface InvoiceCreateBody {
  due_date?: string | null;
  customer_name?: string;
  customer_phone?: string;
  notes?: string;
}

export function createInvoice(folioId: number, body: InvoiceCreateBody = {}): Promise<Invoice> {
  return hotelJson<Invoice>(`${B}/folios/${folioId}/invoices`, { method: "POST", body: JSON.stringify(body) });
}

export function issueInvoice(id: number): Promise<Invoice> {
  return hotelJson<Invoice>(`${B}/invoices/${id}/issue`, { method: "POST", body: "{}" });
}

export function voidInvoice(id: number, reason: string): Promise<Invoice> {
  return hotelJson<Invoice>(`${B}/invoices/${id}/void`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function getInvoicePrint(id: number): Promise<{ document: string; hotel: import("./types").HotelHeader; invoice: Invoice }> {
  return hotelJson(`${B}/invoices/${id}/print`);
}

// --- Expenses ---------------------------------------------------------------

export interface ExpenseListParams {
  status?: string;
  category?: string;
  method?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
}

export function listExpenses(params?: ExpenseListParams): Promise<PaginatedResponse<Expense>> {
  return hotelJson<PaginatedResponse<Expense>>(`${B}/expenses${toQuery(params)}`);
}

export interface ExpenseBody {
  category?: string;
  description: string;
  amount: string;
  method?: string;
  paid_at?: string | null;
  vendor_name?: string;
  reference?: string;
  notes?: string;
  currency?: string;
}

export function createExpense(body: ExpenseBody): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses`, { method: "POST", body: JSON.stringify(body) });
}

export function updateExpense(id: number, body: Partial<ExpenseBody>): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function voidExpense(id: number, reason: string): Promise<Expense> {
  return hotelJson<Expense>(`${B}/expenses/${id}/void`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function getExpenseVoucher(id: number): Promise<{ document: string; hotel: import("./types").HotelHeader; expense: Expense }> {
  return hotelJson(`${B}/expenses/${id}/voucher`);
}
