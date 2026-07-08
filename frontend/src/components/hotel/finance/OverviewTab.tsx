"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, PiggyBank, Receipt, ReceiptText, TrendingUp, Wallet } from "lucide-react";

import { ErrorState, LoadingState, StatCard } from "@/components/ui";
import { getFinanceOverview } from "@/lib/api/finance";
import { messageForError } from "@/lib/api/errors";
import type { FinanceOverview } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t, locale } = useI18n();
  const [data, setData] = useState<FinanceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getFinanceOverview());
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) return <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />;

  const c = data?.currency ?? "USD";
  const m = (v?: string) => (data ? formatMoney(v ?? "0", c, locale) : "—");

  return (
    <section className="stat-grid">
      <StatCard label={t.finance.overview.openFolios} value={data?.open_folios ?? "—"} icon={FileText} tone="info" />
      <StatCard label={t.finance.overview.outstanding} value={m(data?.outstanding_balance)} icon={Wallet} tone="warning" />
      <StatCard label={t.finance.overview.paymentsToday} value={m(data?.payments_today)} icon={Receipt} tone="success" />
      <StatCard label={t.finance.overview.expensesToday} value={m(data?.expenses_today)} icon={PiggyBank} tone="danger" />
      <StatCard label={t.finance.overview.netToday} value={m(data?.net_today)} icon={TrendingUp} tone="primary" />
      <StatCard label={t.finance.overview.issuedInvoices} value={data?.issued_invoices ?? "—"} icon={ReceiptText} tone="neutral" />
    </section>
  );
}
