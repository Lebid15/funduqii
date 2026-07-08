"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeftRight,
  Banknote,
  CalendarCheck2,
  CalendarDays,
  CircleAlert,
  Clock,
  Lock,
} from "lucide-react";

import { ErrorState, LoadingState, WorkflowCard } from "@/components/ui";
import { getShiftsOverview } from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { ShiftsOverview } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t, locale } = useI18n();
  const [data, setData] = useState<ShiftsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getShiftsOverview());
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
  if (error || !data)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error ?? t.errors.generic}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );

  const o = t.shifts.overview;
  const unassignedTotal =
    data.unassigned_movements.payments_count + data.unassigned_movements.expenses_count;
  return (
    <div className="workflow-grid">
      <WorkflowCard
        icon={Clock}
        tone={data.open_shifts > 0 ? "primary" : "neutral"}
        title={o.openShifts}
        value={data.open_shifts}
        description={o.openShiftsHint}
      />
      <WorkflowCard
        icon={CalendarDays}
        tone="info"
        title={o.todayShifts}
        value={data.today_shifts}
        description={o.todayShiftsHint}
      />
      <WorkflowCard
        icon={ArrowLeftRight}
        tone={data.pending_handovers > 0 ? "warning" : "neutral"}
        title={o.pendingHandovers}
        value={data.pending_handovers}
        description={o.pendingHandoversHint}
      />
      <WorkflowCard
        icon={Banknote}
        tone="success"
        title={o.cashExpected}
        value={data.today_cash_expected}
        description={o.cashExpectedHint}
      />
      <WorkflowCard
        icon={CircleAlert}
        tone={unassignedTotal > 0 ? "warning" : "neutral"}
        title={o.unassigned}
        value={unassignedTotal}
        description={o.unassignedHint}
      />
      <WorkflowCard
        icon={CalendarCheck2}
        tone="neutral"
        title={o.lastClose}
        value={
          data.last_daily_close_date
            ? formatDate(data.last_daily_close_date, locale)
            : o.never
        }
        description={o.lastCloseHint}
      />
      <WorkflowCard
        icon={Lock}
        tone={data.today_close_status === "closed" ? "danger" : "neutral"}
        title={o.dayStatus}
        value={
          data.today_close_status
            ? t.shifts.dcStatus[data.today_close_status]
            : o.dayOpen
        }
        description={o.dayStatusHint}
      />
    </div>
  );
}
