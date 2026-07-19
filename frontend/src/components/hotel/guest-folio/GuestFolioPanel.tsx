"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FileText, ShieldAlert, Tags } from "lucide-react";

import { EmptyState, LoadingState, Tabs, type TabItem } from "@/components/ui";
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
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();

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

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "folio" ? <FolioDirectoryTab /> : null}
      {tab === "catalog" ? <CatalogTab /> : null}
    </>
  );
}
