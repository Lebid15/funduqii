"use client";

import { useState } from "react";
import { BedDouble, Building2, LayoutDashboard, Package } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  FloorsTab,
  RoomOperationalBoard,
  RoomTypesTab,
  RoomsTab,
} from "@/components/hotel/rooms";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Rooms console: the OPERATIONAL board first (owner task — live statuses,
 * clickable summaries, rooms grouped by floor), then the management tabs
 * (floors, room types, detailed rooms list) exactly as before.
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

  const tabs: TabItem[] = [
    { key: "overview", label: t.rooms.board.tabTitle, icon: LayoutDashboard },
    { key: "floors", label: t.rooms.tabs.floors, icon: Building2 },
    { key: "types", label: t.rooms.tabs.types, icon: Package },
    { key: "rooms", label: t.rooms.tabs.rooms, icon: BedDouble },
  ];

  return (
    <PageContainer>
      <PageHeader title={t.rooms.title} subtitle={t.rooms.subtitle} />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <RoomOperationalBoard /> : null}
      {tab === "floors" ? <FloorsTab /> : null}
      {tab === "types" ? <RoomTypesTab /> : null}
      {tab === "rooms" ? <RoomsTab /> : null}
    </PageContainer>
  );
}
