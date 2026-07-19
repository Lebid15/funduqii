"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { GuestFolioPanel } from "@/components/hotel/guest-folio/GuestFolioPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Guest folio — the OPERATIONAL surface for posting extra services to an in-house
 * stay's folio and managing the hotel's extra-services catalog. Deliberately
 * SEPARATE from the finance console (FinancePanel stays behind finance.view):
 * a service_orders.create-only user works here without ever seeing folio money.
 * The hotel layout already provides the shell + HotelRouteGuard.
 */
export default function GuestFolioPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.guestFolio.title} subtitle={t.guestFolio.subtitle} />
      <GuestFolioPanel />
    </PageContainer>
  );
}
