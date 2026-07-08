"use client";

import { useState } from "react";
import {
  ArrowLeftRight,
  BedDouble,
  Banknote,
  CalendarCheck,
  ClipboardList,
  LogIn,
  LogOut,
  Printer,
  Receipt,
  UtensilsCrossed,
} from "lucide-react";

import { Button, WorkflowCard } from "@/components/ui";
import { PrintDocumentLayout } from "@/components/ui";
import { PrintModal } from "@/components/hotel/finance/shared";
import { getOverviewReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { ReportState, useReport } from "./shared";

export function OverviewTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const o = t.reports.overview;
  const { data, error, loading, reload } = useReport(getOverviewReport, range);
  const [printOpen, setPrintOpen] = useState(false);

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <div className="cluster">
            <Button
              size="sm"
              variant="secondary"
              icon={Printer}
              onClick={() => setPrintOpen(true)}
            >
              {t.reports.common.print}
            </Button>
          </div>
          <div className="workflow-grid">
            <WorkflowCard
              icon={CalendarCheck}
              tone="info"
              title={o.reservations}
              value={data.reservations_count}
              description={`${o.reservationsHint} (${data.confirmed_reservations_count} / ${data.cancelled_reservations_count})`}
            />
            <WorkflowCard
              icon={LogIn}
              tone="success"
              title={o.arrivals}
              value={data.arrivals_count}
              description={o.arrivalsHint}
            />
            <WorkflowCard
              icon={LogOut}
              tone="neutral"
              title={o.departures}
              value={data.departures_count}
              description={o.departuresHint}
            />
            <WorkflowCard
              icon={BedDouble}
              tone="primary"
              title={o.occupancy}
              value={`${data.occupancy_rate}%`}
              description={o.occupancyHint}
            />
            <WorkflowCard
              icon={Banknote}
              tone="success"
              title={o.payments}
              value={data.total_payments}
              description={o.paymentsHint}
            />
            <WorkflowCard
              icon={Receipt}
              tone="warning"
              title={o.expenses}
              value={data.total_expenses}
              description={o.expensesHint}
            />
            <WorkflowCard
              icon={Banknote}
              tone={data.net_cashflow_simple.startsWith("-") ? "danger" : "success"}
              title={o.net}
              value={data.net_cashflow_simple}
              description={o.netHint}
            />
            <WorkflowCard
              icon={UtensilsCrossed}
              tone="info"
              title={o.services}
              value={data.service_orders_total}
              description={`${o.servicesHint} (${data.service_orders_posted_total})`}
            />
            <WorkflowCard
              icon={ClipboardList}
              tone={
                data.open_housekeeping_tasks +
                  data.open_maintenance_requests +
                  data.open_lost_found_items >
                0
                  ? "warning"
                  : "neutral"
              }
              title={o.operationsOpen}
              value={
                data.open_housekeeping_tasks +
                data.open_maintenance_requests +
                data.open_lost_found_items
              }
              description={o.operationsOpenHint}
            />
            <WorkflowCard
              icon={ArrowLeftRight}
              tone="neutral"
              title={o.shifts}
              value={`${data.open_shifts_count} / ${data.closed_days_count}`}
              description={o.shiftsHint}
            />
          </div>
          <PrintModal
            open={printOpen}
            title={o.printTitle}
            onClose={() => setPrintOpen(false)}
          >
            <PrintDocumentLayout
              hotelName={t.app.name}
              docTitle={o.printTitle}
              docNumber={`${data.date_from} → ${data.date_to}`}
              meta={[
                { label: o.reservations, value: data.reservations_count },
                { label: o.arrivals, value: data.arrivals_count },
                { label: o.departures, value: data.departures_count },
                { label: o.occupancy, value: `${data.occupancy_rate}%` },
                { label: o.inHouse, value: data.in_house_count },
                { label: o.roomsSnapshot, value: data.rooms_total },
              ]}
              totals={[
                { label: o.payments, value: data.total_payments },
                { label: o.expenses, value: data.total_expenses },
                { label: o.net, value: data.net_cashflow_simple },
              ]}
              footer={t.reports.finance.disclaimer}
            />
          </PrintModal>
        </>
      ) : null}
    </ReportState>
  );
}
