"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BellRing,
  CheckCheck,
  ChefHat,
  CircleDollarSign,
  ClipboardList,
  PackageCheck,
  UtensilsCrossed,
} from "lucide-react";

import { ErrorState, LoadingState, WorkflowCard } from "@/components/ui";
import { getServicesOverview } from "@/lib/api/services";
import { messageForError } from "@/lib/api/errors";
import type { ServicesOverview } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t } = useI18n();
  const [data, setData] = useState<ServicesOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getServicesOverview());
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

  return (
    <div className="workflow-grid">
      <WorkflowCard
        icon={ClipboardList}
        tone="info"
        title={t.services.overview.ordersToday}
        value={data.orders_today}
        description={t.services.overview.ordersTodayHint}
      />
      <WorkflowCard
        icon={ChefHat}
        tone="warning"
        title={t.services.overview.preparing}
        value={data.submitted + data.preparing}
        description={t.services.overview.preparingHint}
      />
      <WorkflowCard
        icon={BellRing}
        tone="primary"
        title={t.services.overview.ready}
        value={data.ready}
        description={t.services.overview.readyHint}
      />
      <WorkflowCard
        icon={PackageCheck}
        tone="success"
        title={t.services.overview.delivered}
        value={data.delivered}
        description={t.services.overview.deliveredHint}
      />
      <WorkflowCard
        icon={CheckCheck}
        tone={data.delivered_not_posted > 0 ? "danger" : "neutral"}
        title={t.services.overview.notPosted}
        value={data.delivered_not_posted}
        description={t.services.overview.notPostedHint}
      />
      <WorkflowCard
        icon={CircleDollarSign}
        tone="success"
        title={t.services.overview.postedToday}
        value={data.posted_today_total}
        description={t.services.overview.postedTodayHint}
      />
      <WorkflowCard
        icon={UtensilsCrossed}
        tone="neutral"
        title={t.services.overview.activeItems}
        value={data.active_items}
        description={t.services.overview.activeItemsHint}
      />
    </div>
  );
}
