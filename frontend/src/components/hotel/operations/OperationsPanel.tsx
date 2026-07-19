"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Brush, PackageSearch, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "@/components/ui";
import { cx } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { HousekeepingTab } from "./HousekeepingTab";
import { LostFoundTab } from "./LostFoundTab";
import { MaintenanceTab } from "./MaintenanceTab";

/** EXACTLY three tabs (WP10 §1): Cleaning / Maintenance / Lost & Found. The old
 * Overview + Room-board tabs were removed; their functions were relocated onto
 * the per-tab stat row and the cleaning card. `?tab=` still deep-links the three
 * (topbar quick actions). */
const TAB_KEYS = ["housekeeping", "maintenance", "lostFound"] as const;
type TabKey = (typeof TAB_KEYS)[number];

const TAB_ICONS: Record<TabKey, LucideIcon> = {
  housekeeping: Brush,
  maintenance: Wrench,
  lostFound: PackageSearch,
};

function isTabKey(value: string | null): value is TabKey {
  return value !== null && (TAB_KEYS as readonly string[]).includes(value);
}

export function OperationsPanel() {
  const { t, locale } = useI18n();
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState<TabKey>(isTabKey(requested) ? requested : "housekeeping");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Follow URL changes so a quick action fired while already on this page still
  // lands on its tab (manual clicks stay local).
  useEffect(() => {
    if (isTabKey(requested)) setTab(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);

  const isRtl = locale === "ar";

  function focusTab(index: number) {
    const count = TAB_KEYS.length;
    const clamped = ((index % count) + count) % count;
    const key = TAB_KEYS[clamped];
    setTab(key);
    tabRefs.current[clamped]?.focus();
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const forward = isRtl ? "ArrowLeft" : "ArrowRight";
    const backward = isRtl ? "ArrowRight" : "ArrowLeft";
    switch (event.key) {
      case forward:
        event.preventDefault();
        focusTab(index + 1);
        break;
      case backward:
        event.preventDefault();
        focusTab(index - 1);
        break;
      case "Home":
        event.preventDefault();
        focusTab(0);
        break;
      case "End":
        event.preventDefault();
        focusTab(TAB_KEYS.length - 1);
        break;
      default:
        break;
    }
  }

  return (
    <>
      <div className="tabs" role="tablist" aria-label={t.operations.tablistLabel}>
        {TAB_KEYS.map((key, index) => {
          const active = key === tab;
          return (
            <button
              key={key}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`op-tab-${key}`}
              aria-selected={active}
              // Only ONE tabpanel is mounted at a time (the active tab's), so
              // aria-controls is set ONLY on the active tab — pointing an inactive
              // tab at an unmounted panel id would be a dangling reference (a11y
              // Low). Its panel id appears once the tab becomes active.
              aria-controls={active ? `op-panel-${key}` : undefined}
              tabIndex={active ? 0 : -1}
              className={cx("tabs__tab", active && "tabs__tab--active")}
              onClick={() => setTab(key)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              <Icon icon={TAB_ICONS[key]} size="sm" />
              {t.operations.tabs[key]}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`op-panel-${tab}`}
        aria-labelledby={`op-tab-${tab}`}
        className="op-tabpanel"
        tabIndex={0}
      >
        {tab === "housekeeping" ? <HousekeepingTab /> : null}
        {tab === "maintenance" ? <MaintenanceTab /> : null}
        {tab === "lostFound" ? <LostFoundTab /> : null}
      </div>
    </>
  );
}
