/**
 * Client-side reports API (Phase 13) — READ-ONLY. Calls the same-origin hotel
 * BFF proxy. Every number is computed by the backend (Decimal, hotel-scoped);
 * these helpers never aggregate or compute money themselves. CSV export links
 * point at the same proxy and respect the same filters and permissions.
 */
import { hotelJson } from "./hotelFetch";
import type {
  ComparisonsReport,
  ExpensesReport,
  FinanceOverviewReport,
  FinanceReport,
  FolioBalancesReport,
  GuestsReport,
  OccupancyReport,
  OperationsReport,
  OverviewReport,
  PaymentsReport,
  ReportPage,
  DailyCloseReportRow,
  ReservationsReport,
  RestaurantCafeReport,
  RevenueReport,
  ServicesReport,
  ShiftsReport,
  TaxReport,
} from "./types";

export interface ReportRange {
  date_from?: string;
  date_to?: string;
  page?: number;
}

function toQuery(params?: ReportRange): string {
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

const B = "/reports";

export function getOverviewReport(range?: ReportRange): Promise<OverviewReport> {
  return hotelJson<OverviewReport>(`${B}/overview${toQuery(range)}`);
}

export function getReservationsReport(
  range?: ReportRange,
): Promise<ReservationsReport> {
  return hotelJson<ReservationsReport>(`${B}/reservations${toQuery(range)}`);
}

export function getOccupancyReport(range?: ReportRange): Promise<OccupancyReport> {
  return hotelJson<OccupancyReport>(`${B}/occupancy${toQuery(range)}`);
}

export function getGuestsReport(range?: ReportRange): Promise<GuestsReport> {
  return hotelJson<GuestsReport>(`${B}/guests${toQuery(range)}`);
}

export function getFinanceReport(range?: ReportRange): Promise<FinanceReport> {
  return hotelJson<FinanceReport>(`${B}/finance${toQuery(range)}`);
}

/* --- Finance & Reports final closure — business-date-keyed finance reports.
 * All gated by `reports.finance`; accept ?date_from&date_to (default = the
 * current month by hotel business date). Every money value is a string. */

export function getFinanceOverview(
  range?: ReportRange,
): Promise<FinanceOverviewReport> {
  return hotelJson<FinanceOverviewReport>(`${B}/finance/overview${toQuery(range)}`);
}

export function getRevenueReport(range?: ReportRange): Promise<RevenueReport> {
  return hotelJson<RevenueReport>(`${B}/finance/revenue${toQuery(range)}`);
}

export function getPaymentsReport(range?: ReportRange): Promise<PaymentsReport> {
  return hotelJson<PaymentsReport>(`${B}/finance/payments${toQuery(range)}`);
}

export function getExpensesReport(range?: ReportRange): Promise<ExpensesReport> {
  return hotelJson<ExpensesReport>(`${B}/finance/expenses${toQuery(range)}`);
}

export function getTaxReport(range?: ReportRange): Promise<TaxReport> {
  return hotelJson<TaxReport>(`${B}/finance/taxes${toQuery(range)}`);
}

export function getFolioBalancesReport(
  range?: ReportRange,
): Promise<FolioBalancesReport> {
  return hotelJson<FolioBalancesReport>(`${B}/finance/folios${toQuery(range)}`);
}

export function getRestaurantCafeReport(
  range?: ReportRange,
): Promise<RestaurantCafeReport> {
  return hotelJson<RestaurantCafeReport>(
    `${B}/finance/restaurant-cafe${toQuery(range)}`,
  );
}

/** Comparisons are anchored to the hotel business date; range is ignored. */
export function getComparisonsReport(): Promise<ComparisonsReport> {
  return hotelJson<ComparisonsReport>(`${B}/finance/comparisons`);
}

export function getServicesReport(range?: ReportRange): Promise<ServicesReport> {
  return hotelJson<ServicesReport>(`${B}/services${toQuery(range)}`);
}

export function getOperationsReport(range?: ReportRange): Promise<OperationsReport> {
  return hotelJson<OperationsReport>(`${B}/operations${toQuery(range)}`);
}

export function getShiftsReport(range?: ReportRange): Promise<ShiftsReport> {
  return hotelJson<ShiftsReport>(`${B}/shifts${toQuery(range)}`);
}

export function getDailyCloseReport(
  range?: ReportRange,
): Promise<ReportPage<DailyCloseReportRow>> {
  return hotelJson<ReportPage<DailyCloseReportRow>>(
    `${B}/daily-close${toQuery(range)}`,
  );
}

/** BFF URL for a CSV export — used as a plain link (browser download). */
export function csvExportUrl(
  report: "reservations" | "payments" | "shifts",
  range?: ReportRange,
): string {
  const path =
    report === "payments"
      ? `${B}/finance/payments/export.csv`
      : `${B}/${report}/export.csv`;
  return `/api/hotel${path}${toQuery(range)}`;
}
