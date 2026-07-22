"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { ExpensesPanel } from "@/components/hotel/expenses/ExpensesPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Expenses — the standalone operational surface for recording and managing the
 * hotel's operating expenses (EXPENSES-CLOSURE). Deliberately SEPARATE from the
 * finance console: it is gated on `expenses.*` codes, not `finance.view`, so an
 * expenses-only clerk works here without ever reaching folios/payments/invoices.
 * The hotel layout already provides the shell + HotelRouteGuard.
 */
export default function ExpensesPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.expenses.title} subtitle={t.expenses.subtitle} />
      <ExpensesPanel />
    </PageContainer>
  );
}
