"use client";

import {
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import { getServicesReport, type ReportRange } from "@/lib/api/reports";
import type { ServicesReport } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BucketTable, ReportState, useReport } from "./shared";

type TopItem = ServicesReport["top_items"][number];

export function ServicesTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const s = t.reports.services;
  const { data, error, loading, reload } = useReport(getServicesReport, range);

  const columns: Column<TopItem>[] = [
    { key: "key", header: t.reports.common.key },
    { key: "count", header: t.reports.common.count },
    { key: "quantity", header: t.reports.common.quantity },
    { key: "total", header: t.reports.common.total, render: (r) => r.total ?? "—" },
  ];

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="workflow-grid">
            <StatCard label={s.orders} value={data.orders_count} />
            <StatCard label={s.deliveredPosted} value={data.delivered_posted} />
            <StatCard label={s.deliveredUnposted} value={data.delivered_unposted} />
            <StatCard label={s.postedTotal} value={data.posted_to_folio_total} />
            <StatCard label={s.cancelled} value={data.cancelled_count} />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={s.byStatus}
              rows={data.by_status}
              labelFor={(key) =>
                (t.services.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable title={s.bySource} rows={data.by_source} />
          </div>
          <Card>
            <SectionHeader title={s.topItems} />
            {data.top_items.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={s.topItems}
                columns={columns}
                rows={data.top_items}
                rowKey={(row) => row.key}
              />
            )}
          </Card>
        </>
      ) : null}
    </ReportState>
  );
}
