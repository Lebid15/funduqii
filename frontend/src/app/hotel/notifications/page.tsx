"use client";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { NotificationsPanel } from "@/components/hotel/notifications/NotificationsPanel";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Notifications & activity console (Phase 14). In-app only — no WhatsApp,
 * no email, no push, no chat. Activity is a simplified operational feed,
 * never a legal audit log.
 */
export default function NotificationsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t.notifications.title} subtitle={t.notifications.subtitle} />
      <NotificationsPanel />
    </PageContainer>
  );
}
