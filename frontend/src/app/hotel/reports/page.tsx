"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { ReportsPanel } from "@/components/hotel/reports/ReportsPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Reports console (Phase 13): READ-ONLY operational insight over everything
 * built so far. Not BI, not accounting — every number is computed by the
 * backend, and net movement is deliberately never called profit.
 */
export default function ReportsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.reports.title} subtitle={t.reports.subtitle} />
      <ReportsPanel />
    </PageContainer>
  );
}
