"use client";

import { StatCard } from "@/components/ui";
import { getRevenueReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  AmountTable,
  FinanceMeta,
  ReportState,
  useReport,
  useRevenueLabel,
} from "./shared";

export function RevenueTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const revenueLabel = useRevenueLabel();
  const { data, error, loading, reload } = useReport(getRevenueReport, range);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <FinanceMeta
            sourceStatus={data.source_status}
            daysMissingClose={data.days_missing_close}
            reportingMissing={data.reporting_missing_days}
            manualRoomOnly={!data.data_quality.has_room_charges}
          />
          <div className="workflow-grid">
            <StatCard label={f.grossRevenue} value={data.gross_revenue} />
            <StatCard label={f.adjustments} value={data.adjustments} />
            <StatCard label={f.discounts} value={data.discounts} />
            <StatCard label={f.taxes} value={data.taxes} />
            <StatCard label={f.netRevenue} value={data.net_revenue} tone="success" />
          </div>
          <AmountTable
            title={f.revenueByCategory}
            data={data.by_category}
            keyHeader={f.category}
            valueHeader={t.reports.common.total}
            labelFor={revenueLabel}
          />
        </>
      ) : null}
    </ReportState>
  );
}
