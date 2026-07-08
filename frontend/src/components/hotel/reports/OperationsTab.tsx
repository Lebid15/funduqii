"use client";

import { StatCard } from "@/components/ui";
import { getOperationsReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BucketTable, ReportState, useReport } from "./shared";

export function OperationsTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const o = t.reports.operations;
  const { data, error, loading, reload } = useReport(getOperationsReport, range);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="workflow-grid">
            <StatCard label={o.cleaningDone} value={data.cleaning_completed_count} />
            <StatCard
              label={o.underMaintenance}
              value={data.rooms_under_maintenance_now}
            />
            <StatCard label={o.urgent} value={data.urgent_open_count} />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={o.housekeeping}
              rows={data.housekeeping_by_status}
              labelFor={(key) =>
                (t.operations.hk.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={o.maintenanceStatus}
              rows={data.maintenance_by_status}
              labelFor={(key) =>
                (t.operations.mt.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={o.maintenanceCategory}
              rows={data.maintenance_by_category}
              labelFor={(key) =>
                (t.operations.mt.categories as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={o.maintenancePriority}
              rows={data.maintenance_by_priority}
              labelFor={(key) =>
                (t.operations.priority as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={o.lostFoundStatus}
              rows={data.lost_found_by_status}
              labelFor={(key) =>
                (t.operations.lf.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable
              title={o.lostFoundCategory}
              rows={data.lost_found_by_category}
              labelFor={(key) =>
                (t.operations.lf.categories as Record<string, string>)[key] ?? key
              }
            />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
