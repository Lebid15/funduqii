"use client";

import { useEffect, useState } from "react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { RoomOperationalBoard } from "@/components/hotel/rooms";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Rooms workspace (owner rework): ONE unified surface, no tabs. The board is
 * the whole page — header + action bar, four summary cards, search + filters,
 * and rooms grouped into collapsible floor sections. Floors and room types are
 * managed from the same page via the Settings menu (Modals). CRUD refetches the
 * board itself; returning to the tab pulls the latest via a refresh signal
 * WITHOUT remounting, so active filters, search and open modals survive (this
 * replaced the removed global topbar refresh button).
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const [refreshKey, setRefreshKey] = useState(0);

  // "Pull latest" without a button: when the operator returns to this tab
  // (tab-switch back / minimize-restore), bump a refresh signal the board
  // consumes as a non-destructive REFETCH — its active filters, search and open
  // modals survive (no remount). `visibilitychange` (not raw window focus) fires
  // only on real tab-return, not on every trivial focus event.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") setRefreshKey((k) => k + 1);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  return (
    <PageContainer>
      <PageHeader title={t.rooms.title} subtitle={t.rooms.subtitle} />
      <RoomOperationalBoard refreshSignal={refreshKey} />
    </PageContainer>
  );
}
