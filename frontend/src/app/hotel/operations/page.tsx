"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { OperationsPanel } from "@/components/hotel/operations/OperationsPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Operations console (Phase 10): housekeeping tasks, maintenance requests,
 * lost & found and the room status board. No shifts, no daily close, no
 * inventory — room status changes stay on the backend's controlled path.
 */
export default function OperationsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.operations.title} subtitle={t.operations.subtitle} />
      <OperationsPanel />
    </PageContainer>
  );
}
