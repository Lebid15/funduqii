"use client";

import { StatCard } from "@/components/ui";
import { getExpensesReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { AmountTable, FinanceMeta, ReportState, useReport } from "./shared";

export function ExpensesTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const { data, error, loading, reload } = useReport(getExpensesReport, range);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <FinanceMeta sourceStatus={data.source_status} />
          <div className="workflow-grid">
            <StatCard label={f.gross} value={data.expenses.gross} />
            <StatCard label={f.cash} value={data.expenses.cash} />
            <StatCard label={f.nonCash} value={data.expenses.non_cash} />
            <StatCard
              label={f.reversals}
              value={data.expenses.reversals.amount}
              caption={`${f.count}: ${data.expenses.reversals.count} · ${f.cash}: ${data.expenses.reversals.cash} · ${f.nonCash}: ${data.expenses.reversals.non_cash}`}
            />
            <StatCard
              label={f.voided}
              value={data.expenses.voided.amount}
              caption={`${f.count}: ${data.expenses.voided.count}`}
            />
            <StatCard label={f.net} value={data.expenses.net} tone="warning" />
          </div>
          <div className="workflow-grid">
            <AmountTable
              title={f.byMethod}
              data={data.expenses.by_method}
              keyHeader={f.method}
              valueHeader={f.amount}
            />
            <AmountTable
              title={f.byCategory}
              data={data.expenses.by_category ?? {}}
              keyHeader={f.category}
              valueHeader={f.amount}
            />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
