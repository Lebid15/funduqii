"use client";

import { useCallback, useState } from "react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui";
import { RoomOperationalBoard } from "@/components/hotel/rooms";
import { useGlobalRefresh } from "@/lib/globalRefresh";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Rooms workspace (owner rework): ONE unified surface, no tabs. The board is
 * the whole page — header + action bar, four summary cards, search + filters,
 * and rooms grouped into collapsible floor sections. Floors and room types are
 * managed from the same page via the Settings menu (Modals). The topbar's
 * global refresh remounts the board so everything refetches.
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const [refreshKey, setRefreshKey] = useState(0);

  useGlobalRefresh(
    useCallback(() => setRefreshKey((k) => k + 1), []),
  );

  return (
    <PageContainer>
      <PageHeader title={t.rooms.title} subtitle={t.rooms.subtitle} />
      <RoomOperationalBoard key={refreshKey} />
    </PageContainer>
  );
}
