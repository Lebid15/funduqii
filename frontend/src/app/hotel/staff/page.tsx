"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { StaffPanel } from "@/components/hotel/staff/StaffPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Staff & permissions console (Phase 11). Access is decided by permission
 * grants only — job titles are descriptive labels, and there are no fixed
 * roles anywhere. No shifts, no payroll, no attendance.
 */
export default function StaffPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.staff.title} subtitle={t.staff.subtitle} />
      <StaffPanel />
    </PageContainer>
  );
}
