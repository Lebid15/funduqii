"use client";

import {
  Card,
  DataTable,
  EmptyState,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import { getReservationsReport, type ReportRange } from "@/lib/api/reports";
import type { ReservationsReport } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BucketTable, CountsByDayTable, ReportState, useReport } from "./shared";

type Row = ReservationsReport["list"]["results"][number];

export function ReservationsTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const r = t.reports.reservations;
  const { data, error, loading, reload } = useReport(getReservationsReport, range);

  const columns: Column<Row>[] = [
    { key: "reservation_number", header: r.number },
    { key: "guest_name", header: r.guest },
    {
      key: "status",
      header: t.reports.common.status,
      render: (row) => t.reservations.status[row.status],
    },
    { key: "booking_kind", header: r.kind },
    { key: "check_in_date", header: r.checkIn },
    { key: "check_out_date", header: r.checkOut },
    { key: "nights", header: r.nights },
  ];

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="workflow-grid">
            <StatCard label={r.avgNights} value={data.average_nights} />
          </div>
          <div className="workflow-grid">
            <BucketTable
              title={r.byStatus}
              rows={data.by_status}
              labelFor={(key) =>
                (t.reservations.status as Record<string, string>)[key] ?? key
              }
            />
            <BucketTable title={r.bySource} rows={data.by_source} />
            <BucketTable title={r.byKind} rows={data.by_booking_kind} />
            <BucketTable title={r.byRoomType} rows={data.by_room_type} />
            <CountsByDayTable title={r.arrivalsByDay} days={data.arrivals_by_day} />
            <CountsByDayTable title={r.departuresByDay} days={data.departures_by_day} />
          </div>
          <Card>
            <SectionHeader title={t.reports.tabs.reservations} />
            {data.list.results.length === 0 ? (
              <EmptyState
                title={t.reports.common.empty}
                hint={t.reports.common.emptyHint}
              />
            ) : (
              <DataTable
                caption={t.reports.tabs.reservations}
                columns={columns}
                rows={data.list.results}
                rowKey={(row) => row.id}
              />
            )}
          </Card>
        </>
      ) : null}
    </ReportState>
  );
}
