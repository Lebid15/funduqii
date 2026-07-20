"use client";

import { useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FileText, ShieldAlert, Tags } from "lucide-react";

import { EmptyState, Icon, LoadingState, type TabItem } from "@/components/ui";
import { cx } from "@/lib/utils";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { FolioDirectoryTab } from "./FolioDirectoryTab";
import { CatalogTab } from "./CatalogTab";

/**
 * Which EXISTING permission gates each tab (no new namespace):
 * - `folio` — the operational directory + add/view services. ANY of
 *   service_orders.create / services.view / finance.view (mirrors the backend
 *   folio-directory route perm). Money inside is separately gated on finance.view.
 * - `catalog` — the "Services & Prices" catalog. `services.view` to see it;
 *   create/edit/deactivate are gated per-action inside the tab.
 */
const TAB_ACCESS: Record<string, string[]> = {
  folio: ["service_orders.create", "services.view", "finance.view"],
  catalog: ["services.view"],
};
const TAB_KEYS = Object.keys(TAB_ACCESS);

export function GuestFolioPanel() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Permission-aware tabs (FinancePanel pattern): a user only ever sees (and can
  // deep-link) the tabs their permissions allow; the URL is the single source of
  // truth for the active tab, so a disallowed ?tab= resolves to the first allowed.
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
    // Defensive: the route guard already requires one of the three codes to
    // enter this page at all.
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t.staff.accessDenied.title}
        hint={t.staff.accessDenied.hint}
      />
    );
  }

  const allTabs: TabItem[] = [
    { key: "folio", label: t.guestFolio.tabs.folio, icon: FileText },
    { key: "catalog", label: t.guestFolio.tabs.catalog, icon: Tags },
  ];
  const tabs = allTabs.filter((item) => allowedKeys.includes(item.key));

  function changeTab(key: string) {
    router.replace(`${pathname}?tab=${key}`, { scroll: false });
  }

  const isRtl = locale === "ar";

  function focusTab(index: number) {
    const count = tabs.length;
    if (count === 0) return;
    const clamped = ((index % count) + count) % count;
    changeTab(tabs[clamped].key);
    tabRefs.current[clamped]?.focus();
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    // RTL-aware: in Arabic the visual "next" tab is to the LEFT, so ArrowLeft
    // must advance rather than go back.
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
        focusTab(tabs.length - 1);
        break;
      default:
        break;
    }
  }

  // The shared `ui/Tabs` only emits role=tablist/tab/aria-selected — no tabpanel,
  // no aria-controls/labelledby, no roving tabindex and no arrow-key (hence no
  // RTL-aware) navigation. The complete pattern is implemented LOCALLY here,
  // mirroring OperationsPanel, so the shared component is left untouched.
  return (
    <>
      <div className="tabs" role="tablist" aria-label={t.guestFolio.tablistLabel}>
        {tabs.map((item, index) => {
          const active = item.key === tab;
          return (
            <button
              key={item.key}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`gf-tab-${item.key}`}
              aria-selected={active}
              // Only the ACTIVE tab's panel is mounted, so aria-controls is set
              // only there — pointing an inactive tab at an unmounted id would be
              // a dangling reference.
              aria-controls={active ? `gf-panel-${item.key}` : undefined}
              // Roving tabindex: the tablist is ONE tab stop; arrows move within.
              tabIndex={active ? 0 : -1}
              className={cx("tabs__tab", active && "tabs__tab--active")}
              onClick={() => changeTab(item.key)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              {item.icon ? <Icon icon={item.icon} size="sm" /> : null}
              {item.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`gf-panel-${tab}`}
        aria-labelledby={`gf-tab-${tab}`}
        className="op-tabpanel"
        tabIndex={0}
      >
        {tab === "folio" ? <FolioDirectoryTab /> : null}
        {tab === "catalog" ? <CatalogTab /> : null}
      </div>
    </>
  );
}
