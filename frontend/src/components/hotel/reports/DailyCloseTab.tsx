"use client";

import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  type Column,
} from "@/components/ui";
import { getDailyCloseReport, type ReportRange } from "@/lib/api/reports";
import type { DailyCloseReportRow } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { ReportState, useReport } from "./shared";

export function DailyCloseTab({ range }: { range: ReportRange }) {
  const { t, locale } = useI18n();
  const s = t.reports.shifts;
  const { data, error, loading, reload } = useReport(getDailyCloseReport, range);

  const columns: Column<DailyCloseReportRow>[] = [
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
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <Card>
          <SectionHeader title={s.closedDays} />
          {data.results.length === 0 ? (
            <EmptyState
              title={t.reports.common.empty}
              hint={t.reports.common.emptyHint}
            />
          ) : (
            <DataTable
              caption={s.closedDays}
              columns={columns}
              rows={data.results}
              rowKey={(row) => row.id}
            />
          )}
        </Card>
      ) : null}
    </ReportState>
  );
}
