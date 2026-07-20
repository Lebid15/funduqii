"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CalendarCheck2, Clock, ShieldAlert, UserRound } from "lucide-react";

import { EmptyState, LoadingState, Tabs, type TabItem } from "@/components/ui";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { CurrentShiftTab } from "./CurrentShiftTab";
import { DailyCloseTab } from "./DailyCloseTab";
import { ShiftsTab } from "./ShiftsTab";

/** Which EXISTING permission gates each tab (Phase 11 codes): the shift
 * console tabs belong to `shifts.view`, the daily close to
 * `daily_close.view` — the same split as the sidebar entries. `current` is
 * listed first so it is the resolved default; a stale `?tab=overview|handovers`
 * (both re-homed off the tab bar in the operations-simplification wave) is not
 * an allowed key and cleanly falls back to `current`. `dailyClose` stays
 * mounted here until Section 5 relocates it to its own page. */
const TAB_ACCESS: Record<string, string[]> = {
  current: ["shifts.view"],
  shifts: ["shifts.view"],
  dailyClose: ["daily_close.view"],
};
const TAB_KEYS = Object.keys(TAB_ACCESS);

export function ShiftsPanel() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();

  // Permission-aware tabs with the URL as the single source of truth: a
  // disallowed ?tab= resolves to the first allowed tab — no desync, no loops.
  const allowedKeys = useMemo(
    () =>
      TAB_KEYS.filter(
        (key) => access === null || access.can(...TAB_ACCESS[key]),
      ),
    [access],
  );

  const requested = searchParams.get("tab");
  const tab =
    requested && allowedKeys.includes(requested) ? requested : allowedKeys[0];

  const loading = access !== null && access.loading;
  useEffect(() => {
    if (!loading && tab && requested !== tab) {
      router.replace(`${pathname}?tab=${tab}`, { scroll: false });
    }
  }, [loading, tab, requested, pathname, router]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (!tab) {
    // Defensive: the route guard already requires shifts.view OR
    // daily_close.view to enter this page at all.
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t.staff.accessDenied.title}
        hint={t.staff.accessDenied.hint}
      />
    );
  }

  const allTabs: TabItem[] = [
    { key: "current", label: t.shifts.tabs.current, icon: UserRound },
    { key: "shifts", label: t.shifts.tabs.shifts, icon: Clock },
    { key: "dailyClose", label: t.shifts.tabs.dailyClose, icon: CalendarCheck2 },
  ];
  const tabs = allTabs.filter((item) => allowedKeys.includes(item.key));

  function changeTab(key: string) {
    router.replace(`${pathname}?tab=${key}`, { scroll: false });
  }

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "current" ? <CurrentShiftTab /> : null}
      {tab === "shifts" ? <ShiftsTab /> : null}
      {tab === "dailyClose" ? <DailyCloseTab /> : null}
    </>
  );
}
