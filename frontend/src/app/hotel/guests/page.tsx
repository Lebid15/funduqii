"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { GuestsPanel } from "@/components/hotel/guests/GuestsPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Guests directory (Phase 7). Guest profiles only — no money, no attachments. */
export default function GuestsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.guests.title} subtitle={t.guests.subtitle} />
      <GuestsPanel />
    </PageContainer>
  );
}
