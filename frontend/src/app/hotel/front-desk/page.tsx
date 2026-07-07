"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { FrontDeskPanel } from "@/components/hotel/frontdesk/FrontDeskPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Front desk (Phase 7): arrivals, current residents and departures, with
 * operational check-in / check-out. No money — any billing is a later phase.
 */
export default function FrontDeskPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.frontDesk.title} subtitle={t.frontDesk.subtitle} />
      <FrontDeskPanel />
    </PageContainer>
  );
}
