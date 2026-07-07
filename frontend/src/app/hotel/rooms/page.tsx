"use client";

import { useState } from "react";
import { BedDouble, Building2, LayoutDashboard, Package } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  FloorsTab,
  OverviewTab,
  RoomTypesTab,
  RoomsTab,
} from "@/components/hotel/rooms";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Rooms console (Phase 5): floors, room types and rooms with basic manual
 * status. Inventory only — no reservations, availability, guests or money.
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

  const tabs: TabItem[] = [
    { key: "overview", label: t.rooms.tabs.overview, icon: LayoutDashboard },
    { key: "floors", label: t.rooms.tabs.floors, icon: Building2 },
    { key: "types", label: t.rooms.tabs.types, icon: Package },
    { key: "rooms", label: t.rooms.tabs.rooms, icon: BedDouble },
  ];

  return (
    <PageContainer>
      <PageHeader title={t.rooms.title} subtitle={t.rooms.subtitle} />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "floors" ? <FloorsTab /> : null}
      {tab === "types" ? <RoomTypesTab /> : null}
      {tab === "rooms" ? <RoomsTab /> : null}
    </PageContainer>
  );
}
