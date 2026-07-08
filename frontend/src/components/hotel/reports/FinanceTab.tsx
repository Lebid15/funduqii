"use client";

import { Download } from "lucide-react";

import { Alert, Button, StatCard } from "@/components/ui";
import { csvExportUrl, getFinanceReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { BucketTable, DayTable, ReportState, useReport } from "./shared";

export function FinanceTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const access = useHotelAccess();
  const f = t.reports.finance;
  const { data, error, loading, reload } = useReport(getFinanceReport, range);
  const canExport = !access || access.can("reports.export");

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <Alert tone="warning">{f.disclaimer}</Alert>
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
            <StatCard label={f.payments} value={data.total_payments} />
            <StatCard label={f.expenses} value={data.total_expenses} />
            <StatCard
              label={f.net}
              value={data.net_cashflow_simple}
              tone={data.net_cashflow_simple.startsWith("-") ? "danger" : "success"}
            />
            <StatCard
              label={f.invoices}
              value={data.invoices_issued_count}
              caption={data.invoices_issued_total}
            />
            <StatCard label={f.openFolios} value={data.open_folios_count} />
            <StatCard label={f.foliosClosed} value={data.folios_closed_in_range} />
            <StatCard
              label={f.voided}
              value={
                data.voided.payments + data.voided.expenses + data.voided.charges
              }
              caption={`${f.voidedPayments}: ${data.voided.payments} · ${f.voidedExpenses}: ${data.voided.expenses} · ${f.voidedCharges}: ${data.voided.charges}`}
            />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={f.byMethod}
              rows={data.payments_by_method}
              showTotal
            />
            <BucketTable
              title={f.byCategory}
              rows={data.expenses_by_category}
              showTotal
            />
            <DayTable title={f.paymentsByDay} rows={data.payments_by_day} />
            <DayTable title={f.expensesByDay} rows={data.expenses_by_day} />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
