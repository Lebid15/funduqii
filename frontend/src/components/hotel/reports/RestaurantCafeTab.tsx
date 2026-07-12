"use client";

import { StatCard } from "@/components/ui";
import { getRestaurantCafeReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { FinanceMeta, ReportState, useReport } from "./shared";

export function RestaurantCafeTab({ range }: { range: ReportRange }) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const { data, error, loading, reload } = useReport(
    getRestaurantCafeReport,
    range,
  );

  return (
    <ReportState loading={loading} error={error} onRetry={reload}>
      {data ? (
        <>
          <FinanceMeta sourceStatus={data.source_status} />
          <div className="workflow-grid">
            <StatCard label={f.restaurantSales} value={data.restaurant_sales} />
            <StatCard label={f.cafeSales} value={data.cafe_sales} />
            <StatCard
              label={f.directSettlements}
              value={data.direct_settlements.total}
              caption={`${f.count}: ${data.direct_settlements.count}`}
            />
            <StatCard
              label={f.folioPostings}
              value={data.folio_postings.total}
              caption={`${f.count}: ${data.folio_postings.count}`}
            />
            <StatCard label={f.openOrders} value={data.open_orders_count} />
            <StatCard label={f.cancelledOrders} value={data.cancelled_orders_count} />
          </div>
        </>
      ) : null}
    </ReportState>
  );
}
