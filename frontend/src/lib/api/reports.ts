/**
 * Client-side reports API (Phase 13) — READ-ONLY. Calls the same-origin hotel
 * BFF proxy. Every number is computed by the backend (Decimal, hotel-scoped);
 * these helpers never aggregate or compute money themselves. CSV export links
 * point at the same proxy and respect the same filters and permissions.
 */
import { hotelJson } from "./hotelFetch";
import type {
  FinanceReport,
  GuestsReport,
  OccupancyReport,
  OperationsReport,
  OverviewReport,
  ReportPage,
  DailyCloseReportRow,
  ReservationsReport,
  ServicesReport,
  ShiftsReport,
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
