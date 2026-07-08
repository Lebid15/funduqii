"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BedDouble,
  Brush,
  CircleSlash,
  PackageSearch,
  Sparkles,
  Wrench,
} from "lucide-react";

import { ErrorState, LoadingState, WorkflowCard } from "@/components/ui";
import { getOperationsOverview } from "@/lib/api/operations";
import { messageForError } from "@/lib/api/errors";
import type { OperationsOverview } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t } = useI18n();
  const [data, setData] = useState<OperationsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getOperationsOverview());
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

  const o = t.operations.overview;
  return (
    <div className="workflow-grid">
      <WorkflowCard
        icon={BedDouble}
        tone={data.dirty_rooms > 0 ? "warning" : "neutral"}
        title={o.dirtyRooms}
        value={data.dirty_rooms}
        description={o.dirtyRoomsHint}
      />
      <WorkflowCard
        icon={Brush}
        tone="info"
        title={o.hkPending}
        value={data.hk_pending}
        description={o.hkPendingHint}
      />
      <WorkflowCard
        icon={Sparkles}
        tone="primary"
        title={o.hkInProgress}
        value={data.hk_in_progress}
        description={o.hkInProgressHint}
      />
      <WorkflowCard
        icon={Wrench}
        tone={data.open_maintenance > 0 ? "warning" : "neutral"}
        title={o.openMaintenance}
        value={data.open_maintenance}
        description={o.openMaintenanceHint}
      />
      <WorkflowCard
        icon={CircleSlash}
        tone={data.rooms_under_maintenance > 0 ? "danger" : "neutral"}
        title={o.roomsUnderMaintenance}
        value={data.rooms_under_maintenance}
        description={o.roomsUnderMaintenanceHint}
      />
      <WorkflowCard
        icon={PackageSearch}
        tone="info"
        title={o.lostFoundOpen}
        value={data.lost_found_open}
        description={o.lostFoundOpenHint}
      />
      <WorkflowCard
        icon={AlertTriangle}
        tone={data.urgent_tasks > 0 ? "danger" : "success"}
        title={o.urgentTasks}
        value={data.urgent_tasks}
        description={o.urgentTasksHint}
      />
    </div>
  );
}
