"use client";

import { useCallback, useState } from "react";
import { BedDouble, Building2, LayoutDashboard, Package } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  FloorsTab,
  RoomOperationalBoard,
  RoomTypesTab,
  RoomsTab,
} from "@/components/hotel/rooms";
import { useGlobalRefresh } from "@/lib/globalRefresh";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Rooms console (owner UX round): the OPERATIONAL board tab is pure
 * view/filter — no admin buttons above it. Management actions live in
 * their own tabs (types / floors / rooms). The topbar's global refresh
 * remounts the active tab so everything refetches.
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);

  useGlobalRefresh(
    useCallback(() => setRefreshKey((k) => k + 1), []),
  );

  const tabs: TabItem[] = [
    { key: "overview", label: t.rooms.board.tabTitle, icon: LayoutDashboard },
    { key: "floors", label: t.rooms.tabs.floors, icon: Building2 },
    { key: "types", label: t.rooms.tabs.types, icon: Package },
    { key: "rooms", label: t.rooms.tabs.rooms, icon: BedDouble },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t.rooms.title}
        subtitle={t.rooms.subtitle}
        icon={BedDouble}
        tone="teal"
      />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <RoomOperationalBoard key={refreshKey} /> : null}
      {tab === "floors" ? <FloorsTab key={refreshKey} /> : null}
      {tab === "types" ? <RoomTypesTab key={refreshKey} /> : null}
      {tab === "rooms" ? <RoomsTab key={refreshKey} /> : null}
    </PageContainer>
  );
}
