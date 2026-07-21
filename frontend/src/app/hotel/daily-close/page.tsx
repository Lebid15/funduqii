"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { DailyClosePanel } from "@/components/hotel/daily-close/DailyClosePanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Daily close — its OWN operational page (owner decision, operations-simplification
 * wave §5). Promoted out of the shifts console so a `daily_close.view` member can
 * reach the atomic business-day close here WITHOUT holding `shifts.view`. Entry is
 * gated by the hotel layout's HotelRouteGuard via `/hotel/daily-close` →
 * ["daily_close.view"] (hotelRouteAccess.ts). The close itself remains a single
 * atomic backend operation — this surface only previews it (read-only), triggers
 * it behind a final confirm, prints the stored statement, and lists closed days.
 */
export default function DailyClosePage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.shifts.dc.title} subtitle={t.shifts.dc.subtitle} />
      <DailyClosePanel />
    </PageContainer>
  );
}
