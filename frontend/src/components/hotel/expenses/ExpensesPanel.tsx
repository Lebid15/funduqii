"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ReceiptText, ShieldAlert, Tags } from "lucide-react";

import { EmptyState, LoadingState, Tabs, type TabItem } from "@/components/ui";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { ExpensesTab } from "./ExpensesTab";
import { ExpenseTypesTab } from "./ExpenseTypesTab";

/** Which permission gates each tab (EXPENSES-CLOSURE codes):
 * - `expenses` — the ledger of vouchers. `expenses.view`.
 * - `types` — the manageable expense-type catalog. `expenses.manage_types`. */
const TAB_ACCESS: Record<string, string[]> = {
  expenses: ["expenses.view"],
  types: ["expenses.manage_types"],
};
const TAB_KEYS = Object.keys(TAB_ACCESS);

export function ExpensesPanel() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();

  // Permission-aware tabs (FinancePanel pattern): a user only ever sees (and can
  // deep-link) the tabs their permissions allow. The URL is the single source of
  // truth for the active tab, so a disallowed ?tab= resolves to the first allowed
  // tab — no state to desync, no update loops.
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
    // Defensive: the route guard already requires expenses.view to enter at all.
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t.expenses.accessDenied.title}
        hint={t.expenses.accessDenied.hint}
      />
    );
  }

  const allTabs: TabItem[] = [
    { key: "expenses", label: t.expenses.tabs.expenses, icon: ReceiptText },
    { key: "types", label: t.expenses.tabs.types, icon: Tags },
  ];
  const tabs = allTabs.filter((item) => allowedKeys.includes(item.key));

  function changeTab(key: string) {
    router.replace(`${pathname}?tab=${key}`, { scroll: false });
  }

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "expenses" ? <ExpensesTab /> : null}
      {tab === "types" ? <ExpenseTypesTab /> : null}
    </>
  );
}
