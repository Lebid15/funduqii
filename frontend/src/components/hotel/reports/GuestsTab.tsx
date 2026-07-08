"use client";

import {
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import { getGuestsReport, type ReportRange } from "@/lib/api/reports";
import type { GuestsReport } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BucketTable, ReportState, useReport } from "./shared";

type Row = GuestsReport["list"]["results"][number];

export function GuestsTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const g = t.reports.guests;
  const { data, error, loading, reload } = useReport(getGuestsReport, range);

  const columns: Column<Row>[] = [
    { key: "full_name", header: g.name },
    { key: "nationality", header: g.nationality, render: (r) => r.nationality || "—" },
    { key: "phone", header: g.phone, render: (r) => r.phone || "—" },
    { key: "created_at", header: g.created },
  ];

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="workflow-grid">
            <StatCard label={g.newGuests} value={data.new_guests_count} />
            <StatCard label={g.repeat} value={data.repeat_guests_count} />
            <StatCard label={g.residents} value={data.current_residents_count} />
            <StatCard label={g.checkedOut} value={data.checked_out_count} />
          </div>
          <div className="workflow-grid">
            <BucketTable title={g.byNationality} rows={data.by_nationality} />
          </div>
          <Card>
            <SectionHeader title={t.reports.tabs.guests} />
            {data.list.results.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={t.reports.tabs.guests}
                columns={columns}
                rows={data.list.results}
                rowKey={(row) => row.id}
              />
            )}
          </Card>
        </>
      ) : null}
    </ReportState>
  );
}
