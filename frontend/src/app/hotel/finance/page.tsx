"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { FinancePanel } from "@/components/hotel/finance/FinancePanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Finance console (Phase 8): folios, charges, payments, invoices and expenses.
 * Internal accounting only — no payment gateway, no external integration.
 */
export default function FinancePage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.finance.title} subtitle={t.finance.subtitle} />
      <FinancePanel />
    </PageContainer>
  );
}
