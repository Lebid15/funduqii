"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { BedDouble, Brush, LayoutDashboard, PackageSearch, Wrench } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { HousekeepingTab } from "./HousekeepingTab";
import { LostFoundTab } from "./LostFoundTab";
import { MaintenanceTab } from "./MaintenanceTab";
import { OverviewTab } from "./OverviewTab";
import { RoomBoardTab } from "./RoomBoardTab";

const TAB_KEYS = ["overview", "housekeeping", "maintenance", "lostFound", "roomBoard"];

export function OperationsPanel() {
  const { t } = useI18n();
  // Deep-linkable initial tab (?tab=maintenance — the topbar quick actions):
  // read once on mount, tabs themselves stay local state as before.
  const requested = useSearchParams().get("tab");
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "overview",
  );

  const tabs: TabItem[] = [
    { key: "overview", label: t.operations.tabs.overview, icon: LayoutDashboard },
    { key: "housekeeping", label: t.operations.tabs.housekeeping, icon: Brush },
    { key: "maintenance", label: t.operations.tabs.maintenance, icon: Wrench },
    { key: "lostFound", label: t.operations.tabs.lostFound, icon: PackageSearch },
    { key: "roomBoard", label: t.operations.tabs.roomBoard, icon: BedDouble },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "housekeeping" ? <HousekeepingTab /> : null}
      {tab === "maintenance" ? <MaintenanceTab /> : null}
      {tab === "lostFound" ? <LostFoundTab /> : null}
      {tab === "roomBoard" ? <RoomBoardTab /> : null}
    </>
  );
}
