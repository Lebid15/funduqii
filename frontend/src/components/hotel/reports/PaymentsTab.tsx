"use client";

import { Download } from "lucide-react";

import { Button, StatCard } from "@/components/ui";
import {
  csvExportUrl,
  getPaymentsReport,
  type ReportRange,
} from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { AmountTable, FinanceMeta, ReportState, useReport } from "./shared";

export function PaymentsTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const access = useHotelAccess();
  const f = t.reports.fin;
  const { data, error, loading, reload } = useReport(getPaymentsReport, range);
  const canExport = !access || access.can("reports.export");

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <FinanceMeta sourceStatus={data.source_status} />
          {canExport ? (
            <div className="cluster">
              <a href={csvExportUrl("payments", range)} download>
                <Button size="sm" variant="secondary" icon={Download}>
                  {t.reports.common.exportCsv}
                </Button>
              </a>
            </div>
          ) : null}
          <div className="workflow-grid">
            <StatCard label={f.gross} value={data.payments.gross} />
            <StatCard label={f.cash} value={data.payments.cash} />
            <StatCard label={f.nonCash} value={data.payments.non_cash} />
            <StatCard
              label={f.reversals}
              value={data.payments.reversals.amount}
              caption={`${f.count}: ${data.payments.reversals.count} · ${f.cash}: ${data.payments.reversals.cash} · ${f.nonCash}: ${data.payments.reversals.non_cash}`}
            />
            <StatCard
              label={f.voided}
              value={data.payments.voided.amount}
              caption={`${f.count}: ${data.payments.voided.count}`}
            />
            <StatCard label={f.net} value={data.payments.net} tone="success" />
          </div>
          <div className="workflow-grid">
            <AmountTable
              title={f.byMethod}
              data={data.payments.by_method}
              keyHeader={f.method}
              valueHeader={f.amount}
            />
          </div>
          <div className="workflow-grid">
            <StatCard
              label={f.unassignedPayments}
              value={data.unassigned_movements.payments_total}
              caption={`${f.count}: ${data.unassigned_movements.payments_count}`}
            />
            <StatCard
              label={f.unassignedExpenses}
              value={data.unassigned_movements.expenses_total}
              caption={`${f.count}: ${data.unassigned_movements.expenses_count}`}
            />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
