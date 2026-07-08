"use client";

import { Alert, StatCard } from "@/components/ui";
import { getOccupancyReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BucketTable, CountsByDayTable, ReportState, useReport } from "./shared";

export function OccupancyTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const o = t.reports.occupancy;
  const { data, error, loading, reload } = useReport(getOccupancyReport, range);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <Alert tone="info">{o.note}</Alert>
          <div className="workflow-grid">
            <StatCard label={o.rate} value={`${data.occupancy_rate}%`} />
            <StatCard label={o.capacity} value={data.rooms_capacity} />
            <StatCard label={o.inHouseNow} value={data.in_house_now} />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={o.roomStatusNow}
              rows={Object.entries(data.room_status_now).map(([key, count]) => ({
                key,
                count,
              }))}
              labelFor={(key) =>
                (t.rooms.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable title={o.byRoomType} rows={data.stays_by_room_type} />
            <CountsByDayTable title={o.byDay} days={data.occupied_by_day} />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
