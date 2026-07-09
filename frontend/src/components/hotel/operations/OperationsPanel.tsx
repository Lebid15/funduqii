"use client";

import { useEffect, useState } from "react";
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
  // Deep-linkable tab (?tab=maintenance — the topbar quick actions): initial
  // read + follow URL changes so a quick action fired while ALREADY on this
  // page still lands on its tab. Manual tab clicks stay local as before.
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "overview",
  );
  useEffect(() => {
    if (requested && TAB_KEYS.includes(requested)) setTab(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);

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
