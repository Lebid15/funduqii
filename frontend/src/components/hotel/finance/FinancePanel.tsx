"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  FileText,
  LayoutDashboard,
  Receipt,
  ReceiptText,
  ShieldAlert,
} from "lucide-react";

import { EmptyState, LoadingState, Tabs, type TabItem } from "@/components/ui";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { OverviewTab } from "./OverviewTab";
import { FoliosTab } from "./FoliosTab";
import { PaymentsTab } from "./PaymentsTab";
import { InvoicesTab } from "./InvoicesTab";

/** Which EXISTING permission gates each tab (Phase 11 codes). Expenses moved to
 * the standalone `/hotel/expenses` section (EXPENSES-CLOSURE) and is no longer a
 * finance tab. */
const TAB_ACCESS: Record<string, string[]> = {
  overview: ["finance.view"],
  folios: ["finance.view"],
  payments: ["finance.view"],
  invoices: ["finance.view"],
};
const TAB_KEYS = Object.keys(TAB_ACCESS);

export function FinancePanel() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();

  // Permission-aware tabs: a user only ever sees (and can deep-link) the
  // tabs their permissions allow. The URL is the single source of truth for
  // the active tab, so a disallowed ?tab= simply resolves to the first
  // allowed tab — no state to desync, no update loops.
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

  // Keep the URL normalized to the resolved tab (also fixes the sidebar's
  // active state after a disallowed deep link). Guarded: it only fires when
  // the URL differs from the resolved tab, and after it does they match.
  const loading = access !== null && access.loading;
  useEffect(() => {
    if (!loading && tab && requested !== tab) {
      router.replace(`${pathname}?tab=${tab}`, { scroll: false });
    }
  }, [loading, tab, requested, pathname, router]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (!tab) {
    // Defensive: the route guard already requires finance.view OR
    // expenses.view to enter this page at all.
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t.staff.accessDenied.title}
        hint={t.staff.accessDenied.hint}
      />
    );
  }

  const allTabs: TabItem[] = [
    { key: "overview", label: t.finance.tabs.overview, icon: LayoutDashboard },
    { key: "folios", label: t.finance.tabs.folios, icon: FileText },
    { key: "payments", label: t.finance.tabs.payments, icon: Receipt },
    { key: "invoices", label: t.finance.tabs.invoices, icon: ReceiptText },
  ];
  const tabs = allTabs.filter((item) => allowedKeys.includes(item.key));

  function changeTab(key: string) {
    router.replace(`${pathname}?tab=${key}`, { scroll: false });
  }

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "folios" ? <FoliosTab /> : null}
      {tab === "payments" ? <PaymentsTab /> : null}
      {tab === "invoices" ? <InvoicesTab /> : null}
    </>
  );
}
