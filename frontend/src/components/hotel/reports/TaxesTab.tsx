"use client";

import { StatCard } from "@/components/ui";
import { getTaxReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  AmountTable,
  FinanceMeta,
  ReportState,
  useReport,
  useRevenueLabel,
} from "./shared";

export function TaxesTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const revenueLabel = useRevenueLabel();
  const { data, error, loading, reload } = useReport(getTaxReport, range);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <FinanceMeta
            sourceStatus={data.source_status}
            reportingMissing={data.reporting_missing_days}
          />
          <div className="workflow-grid">
            <StatCard label={f.totalTax} value={data.total_tax} />
            <StatCard label={f.netRevenueExTax} value={data.net_revenue_ex_tax} />
          </div>
          <AmountTable
            title={f.taxableRevenue}
            data={data.by_category_revenue}
            keyHeader={f.category}
            valueHeader={t.reports.common.total}
            labelFor={revenueLabel}
          />
        </>
      ) : null}
    </ReportState>
  );
}
