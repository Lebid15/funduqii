"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  Bell,
  CalendarDays,
  ShieldAlert,
} from "lucide-react";

import { ErrorState, LoadingState, WorkflowCard } from "@/components/ui";
import { getNotificationsOverview } from "@/lib/api/notifications";
import { messageForError } from "@/lib/api/errors";
import type { NotificationsOverview } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t } = useI18n();
  const o = t.notifications.overview;
  const [data, setData] = useState<NotificationsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getNotificationsOverview());
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
        icon={Bell}
        tone={data.unread_count > 0 ? "primary" : "neutral"}
        title={o.unread}
        value={data.unread_count}
        description={o.unreadHint}
      />
      <WorkflowCard
        icon={AlertTriangle}
        tone={data.warning_count > 0 ? "warning" : "neutral"}
        title={o.warnings}
        value={data.warning_count}
        description={o.warningsHint}
      />
      <WorkflowCard
        icon={ShieldAlert}
        tone={data.danger_count > 0 ? "danger" : "neutral"}
        title={o.dangers}
        value={data.danger_count}
        description={o.dangersHint}
      />
      <WorkflowCard
        icon={CalendarDays}
        tone="info"
        title={o.today}
        value={data.today_notifications_count}
        description={o.todayHint}
      />
      <WorkflowCard
        icon={Archive}
        tone="neutral"
        title={o.archived}
        value={data.archived_count}
        description={o.archivedHint}
      />
      <WorkflowCard
        icon={Activity}
        tone="info"
        title={o.activityToday}
        value={data.recent_activity_count}
        description={o.activityTodayHint}
      />
    </div>
  );
}
