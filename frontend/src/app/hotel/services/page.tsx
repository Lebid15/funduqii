"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { ServicesPanel } from "@/components/hotel/services/ServicesPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Services console (Phase 9): restaurant / café / room-service catalog and
 * internal orders that post to the guest folio. No POS, no inventory, no
 * direct payment — finance stays the only money surface.
 */
export default function ServicesPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.services.title} subtitle={t.services.subtitle} />
      <ServicesPanel />
    </PageContainer>
  );
}
