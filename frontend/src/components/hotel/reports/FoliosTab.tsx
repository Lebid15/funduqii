"use client";

import {
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import { getFolioBalancesReport, type ReportRange } from "@/lib/api/reports";
import type { ForeignCurrencyFolio } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { ReportState, useReport } from "./shared";

export function FoliosTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const { data, error, loading, reload } = useReport(getFolioBalancesReport, range);

  const columns: Column<ForeignCurrencyFolio>[] = [
    { key: "currency", header: f.currency },
    { key: "count", header: f.count },
    { key: "balance", header: f.balance, align: "end" },
  ];

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="workflow-grid">
            <StatCard
              label={f.openFolios}
              value={data.open_folios_count}
              caption={f.currency + ": " + data.currency}
            />
            <StatCard label={f.totalBalance} value={data.total_balance} />
            <StatCard
              label={f.positiveBalance}
              value={data.positive_balance_amount}
              caption={`${f.count}: ${data.positive_balance_count}`}
              tone="success"
            />
            <StatCard
              label={f.negativeBalance}
              value={data.negative_balance_amount}
              caption={`${f.count}: ${data.negative_balance_count}`}
              tone="danger"
            />
            <StatCard label={f.zeroBalance} value={data.zero_balance_count} />
            <StatCard label={f.closedInRange} value={data.closed_in_range} />
          </div>
          <Card>
            <SectionHeader title={f.foreignCurrency} />
            {data.foreign_currency_folios.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={f.foreignCurrency}
                columns={columns}
                rows={data.foreign_currency_folios}
                rowKey={(row) => row.currency}
              />
            )}
          </Card>
        </>
      ) : null}
    </ReportState>
  );
}
