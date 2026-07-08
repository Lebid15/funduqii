"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ShieldCheck,
  ShieldOff,
  UserCheck,
  UserCog,
  UserX,
  Users,
} from "lucide-react";

import { ErrorState, LoadingState, WorkflowCard } from "@/components/ui";
import { getStaffOverview } from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type { StaffOverview } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function OverviewTab() {
  const { t } = useI18n();
  const [data, setData] = useState<StaffOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getStaffOverview());
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

  const o = t.staff.overview;
  return (
    <div className="workflow-grid">
      <WorkflowCard
        icon={Users}
        tone="info"
        title={o.total}
        value={data.total_staff}
        description={o.totalHint}
      />
      <WorkflowCard
        icon={UserCheck}
        tone="success"
        title={o.active}
        value={data.active_staff}
        description={o.activeHint}
      />
      <WorkflowCard
        icon={UserX}
        tone={data.inactive_staff > 0 ? "warning" : "neutral"}
        title={o.inactive}
        value={data.inactive_staff}
        description={o.inactiveHint}
      />
      <WorkflowCard
        icon={UserCog}
        tone="primary"
        title={o.managers}
        value={data.managers}
        description={o.managersHint}
      />
      <WorkflowCard
        icon={ShieldCheck}
        tone="success"
        title={o.withPermissions}
        value={data.staff_with_permissions}
        description={o.withPermissionsHint}
      />
      <WorkflowCard
        icon={ShieldOff}
        tone={data.staff_without_permissions > 0 ? "warning" : "neutral"}
        title={o.withoutPermissions}
        value={data.staff_without_permissions}
        description={o.withoutPermissionsHint}
      />
    </div>
  );
}
