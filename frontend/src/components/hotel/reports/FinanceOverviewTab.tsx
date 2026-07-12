"use client";

import {
  Card,
  DataTable,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import {
  getComparisonsReport,
  getFinanceOverview,
  type ReportRange,
} from "@/lib/api/reports";
import type { ComparisonMetric, ComparisonMetrics } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  AmountTable,
  FinanceMeta,
  ReportState,
  useReport,
  useRevenueLabel,
} from "./shared";

type CmpRow = { key: string; label: string; metric: ComparisonMetric };

function ComparisonTable({
  title,
  metrics,
}: {
  title: string;
  metrics: ComparisonMetrics;
}) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const rows: CmpRow[] = [
    { key: "revenue_total", label: f.revenueTotal, metric: metrics.revenue_total },
    { key: "net_payments", label: f.netPayments, metric: metrics.net_payments },
    { key: "net_expenses", label: f.netExpenses, metric: metrics.net_expenses },
    { key: "taxes", label: f.taxes, metric: metrics.taxes },
  ];
  const columns: Column<CmpRow>[] = [
    { key: "label", header: f.metric, render: (r) => r.label },
    { key: "current", header: f.current, align: "end", render: (r) => r.metric.current },
    { key: "previous", header: f.previous, align: "end", render: (r) => r.metric.previous },
    { key: "delta", header: f.delta, align: "end", render: (r) => r.metric.delta },
    {
      key: "deltaPct",
      header: f.deltaPct,
      align: "end",
      render: (r) => (r.metric.delta_pct === null ? "—" : `${r.metric.delta_pct}%`),
    },
  ];
  return (
    <Card>
      <SectionHeader title={title} />
      <DataTable caption={title} columns={columns} rows={rows} rowKey={(r) => r.key} />
    </Card>
  );
}

export function FinanceOverviewTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const revenueLabel = useRevenueLabel();
  const { data, error, loading, reload } = useReport(getFinanceOverview, range);
  const cmp = useReport(getComparisonsReport, range);

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
            <StatCard label={f.totalRevenue} value={data.kpis.total_revenue} />
            <StatCard label={f.roomRevenue} value={data.kpis.room_revenue} />
            <StatCard label={f.restaurantRevenue} value={data.kpis.restaurant_revenue} />
            <StatCard label={f.cafeRevenue} value={data.kpis.cafe_revenue} />
            <StatCard label={f.occupancy} value={`${data.occupancy}%`} />
            <StatCard label={f.adr} value={data.adr} />
            <StatCard label={f.revpar} value={data.revpar} />
            <StatCard label={f.taxes} value={data.taxes} />
            <StatCard
              label={f.netCashflow}
              value={data.net_cashflow}
              tone={data.net_cashflow.startsWith("-") ? "danger" : "success"}
            />
            <StatCard label={f.openFolioBalance} value={data.open_folio_balance} />
          </div>

          <div className="workflow-grid">
            <StatCard
              label={f.netPayments}
              value={data.net_payments}
              caption={`${f.gross}: ${data.gross_payments} · ${f.reversals}: ${data.payment_reversals}`}
              tone="success"
            />
            <StatCard
              label={f.netExpenses}
              value={data.net_expenses}
              caption={`${f.gross}: ${data.gross_expenses} · ${f.reversals}: ${data.expense_reversals}`}
              tone="warning"
            />
          </div>

          <AmountTable
            title={f.revenueByCategory}
            data={data.revenue}
            keyHeader={f.category}
            valueHeader={t.reports.common.total}
            labelFor={revenueLabel}
          />

          {cmp.data ? (
            <div className="workflow-grid">
              <ComparisonTable
                title={f.dayVsPrevious}
                metrics={cmp.data.day_vs_previous}
              />
              <ComparisonTable
                title={f.mtdVsPreviousMonth}
                metrics={cmp.data.mtd_vs_previous_month}
              />
            </div>
          ) : null}
        </>
      ) : null}
    </ReportState>
  );
}
