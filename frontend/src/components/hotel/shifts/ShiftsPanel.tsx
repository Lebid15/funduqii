"use client";

import { useState } from "react";
import { ArrowLeftRight, CalendarCheck2, Clock, LayoutDashboard, UserRound } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { CurrentShiftTab } from "./CurrentShiftTab";
import { DailyCloseTab } from "./DailyCloseTab";
import { HandoversTab } from "./HandoversTab";
import { OverviewTab } from "./OverviewTab";
import { ShiftsTab } from "./ShiftsTab";

export function ShiftsPanel() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

  const tabs: TabItem[] = [
    { key: "overview", label: t.shifts.tabs.overview, icon: LayoutDashboard },
    { key: "current", label: t.shifts.tabs.current, icon: UserRound },
    { key: "shifts", label: t.shifts.tabs.shifts, icon: Clock },
    { key: "handovers", label: t.shifts.tabs.handovers, icon: ArrowLeftRight },
    { key: "dailyClose", label: t.shifts.tabs.dailyClose, icon: CalendarCheck2 },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "current" ? <CurrentShiftTab /> : null}
      {tab === "shifts" ? <ShiftsTab /> : null}
      {tab === "handovers" ? <HandoversTab /> : null}
      {tab === "dailyClose" ? <DailyCloseTab /> : null}
    </>
  );
}
