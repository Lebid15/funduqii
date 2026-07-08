"use client";

import { Download } from "lucide-react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import {
  csvExportUrl,
  getDailyCloseReport,
  getShiftsReport,
  type ReportRange,
} from "@/lib/api/reports";
import type { DailyCloseReportRow, ShiftsReport } from "@/lib/api/types";
import { formatDateTime, shiftStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { BucketTable, ReportState, useReport } from "./shared";

type ShiftRow = ShiftsReport["shifts"][number];

export function ShiftsTab({ range }: { range: ReportRange }) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const s = t.reports.shifts;
  const shiftsReport = useReport(getShiftsReport, range);
  const closesReport = useReport(getDailyCloseReport, range);
  const canExport = !access || access.can("reports.export");

  const shiftColumns: Column<ShiftRow>[] = [
    { key: "shift_number", header: s.number },
    { key: "business_date", header: s.businessDate },
    { key: "responsible", header: s.responsible },
    {
      key: "status",
      header: t.reports.common.status,
      render: (r) => (
        <Badge tone={shiftStatusTone(r.status)}>{t.shifts.status[r.status]}</Badge>
      ),
    },
    { key: "opening_cash", header: s.opening },
    { key: "expected_cash", header: s.expected },
    { key: "actual_cash", header: s.actual, render: (r) => r.actual_cash ?? "—" },
    {
      key: "cash_difference",
      header: s.difference,
      render: (r) => (
        <Badge tone={r.cash_difference === "0.00" ? "success" : "warning"}>
          {r.cash_difference}
        </Badge>
      ),
    },
    { key: "difference_reason", header: s.reason, render: (r) => r.difference_reason || "—" },
  ];

  const closeColumns: Column<DailyCloseReportRow>[] = [
    { key: "close_number", header: s.dcNumber },
    { key: "business_date", header: s.businessDate },
    {
      key: "status",
      header: t.reports.common.status,
      render: (r) => (
        <Badge tone={r.status === "closed" ? "success" : "warning"}>
          {t.shifts.dcStatus[r.status]}
        </Badge>
      ),
    },
    { key: "closed_by", header: s.dcClosedBy, render: (r) => r.closed_by || "—" },
    {
      key: "closed_at",
      header: s.dcClosedAt,
      render: (r) => formatDateTime(r.closed_at, locale),
    },
  ];

  return (
    <ReportState
      loading={shiftsReport.loading}
      error={shiftsReport.error}
      onRetry={shiftsReport.reload}
    >
      {shiftsReport.data ? (
        <>
          {canExport ? (
            <div className="cluster">
              <a href={csvExportUrl("shifts", range)} download>
                <Button size="sm" variant="secondary" icon={Download}>
                  {t.reports.common.exportCsv}
                </Button>
              </a>
            </div>
          ) : null}
          <div className="workflow-grid">
            <StatCard label={s.closed} value={shiftsReport.data.closed_shifts_count} />
            <StatCard
              label={s.withDifference}
              value={shiftsReport.data.shifts_with_difference}
            />
            <StatCard label={s.expected} value={shiftsReport.data.total_expected_cash} />
            <StatCard label={s.actual} value={shiftsReport.data.total_actual_cash} />
            <StatCard
              label={s.difference}
              value={shiftsReport.data.total_cash_difference}
              tone={
                shiftsReport.data.total_cash_difference === "0.00"
                  ? "success"
                  : "warning"
              }
            />
            <StatCard
              label={s.unassigned}
              value={
                shiftsReport.data.unassigned_movements.payments_count +
                shiftsReport.data.unassigned_movements.expenses_count
              }
              caption={`${t.reports.finance.payments}: ${shiftsReport.data.unassigned_movements.payments_total} · ${t.reports.finance.expenses}: ${shiftsReport.data.unassigned_movements.expenses_total}`}
            />
            <StatCard label={s.closedDays} value={shiftsReport.data.closed_days_count} />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={s.byStatus}
              rows={shiftsReport.data.shifts_by_status}
              labelFor={(key) =>
                (t.shifts.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={s.handovers}
              rows={shiftsReport.data.handovers_by_status}
              labelFor={(key) =>
                (t.shifts.hoStatus as Record<string, string>)[key] ?? key
              }
            />
          </div>
          <Card>
            <SectionHeader title={t.shifts.list.title} />
            {shiftsReport.data.shifts.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={t.shifts.list.title}
                columns={shiftColumns}
                rows={shiftsReport.data.shifts}
                rowKey={(row) => row.shift_number}
              />
            )}
          </Card>
          <Card>
            <SectionHeader title={s.closedDays} />
            {closesReport.loading || closesReport.error || !closesReport.data ? null : closesReport
                .data.results.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={s.closedDays}
                columns={closeColumns}
                rows={closesReport.data.results}
                rowKey={(row) => row.id}
              />
            )}
          </Card>
        </>
      ) : null}
    </ReportState>
  );
}
