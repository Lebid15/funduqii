"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { ShiftsPanel } from "@/components/hotel/shifts/ShiftsPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Shifts console (Phase 12): working shifts with a cash drawer, shift
 * handover, and the operational daily close. No attendance, no payroll, no
 * HR — and never a source of financial truth (finance records stay that).
 */
export default function ShiftsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.shifts.title} subtitle={t.shifts.subtitle} />
      <ShiftsPanel />
    </PageContainer>
  );
}
