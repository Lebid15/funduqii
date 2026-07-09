"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, CalendarCheck2, Clock, LayoutDashboard, UserRound } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { CurrentShiftTab } from "./CurrentShiftTab";
import { DailyCloseTab } from "./DailyCloseTab";
import { HandoversTab } from "./HandoversTab";
import { OverviewTab } from "./OverviewTab";
import { ShiftsTab } from "./ShiftsTab";

const TAB_KEYS = ["overview", "current", "shifts", "handovers", "dailyClose"];

export function ShiftsPanel() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // "Daily close" is a separate sidebar entry deep-linking ?tab=dailyClose
  // on this shared page; the URL mirrors internal tab switches so the
  // sidebar's active state stays truthful.
  const requested = searchParams.get("tab");
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "overview",
  );

  useEffect(() => {
    if (requested && TAB_KEYS.includes(requested)) setTab(requested);
  }, [requested]);

  function changeTab(key: string) {
    setTab(key);
    router.replace(`${pathname}?tab=${key}`, { scroll: false });
  }

  const tabs: TabItem[] = [
    { key: "overview", label: t.shifts.tabs.overview, icon: LayoutDashboard },
    { key: "current", label: t.shifts.tabs.current, icon: UserRound },
    { key: "shifts", label: t.shifts.tabs.shifts, icon: Clock },
    { key: "handovers", label: t.shifts.tabs.handovers, icon: ArrowLeftRight },
    { key: "dailyClose", label: t.shifts.tabs.dailyClose, icon: CalendarCheck2 },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "current" ? <CurrentShiftTab /> : null}
      {tab === "shifts" ? <ShiftsTab /> : null}
      {tab === "handovers" ? <HandoversTab /> : null}
      {tab === "dailyClose" ? <DailyCloseTab /> : null}
    </>
  );
}
