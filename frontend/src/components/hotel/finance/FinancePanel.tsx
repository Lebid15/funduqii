"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FileText, LayoutDashboard, PiggyBank, Receipt, ReceiptText } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { OverviewTab } from "./OverviewTab";
import { FoliosTab } from "./FoliosTab";
import { PaymentsTab } from "./PaymentsTab";
import { InvoicesTab } from "./InvoicesTab";
import { ExpensesTab } from "./ExpensesTab";

const TAB_KEYS = ["overview", "folios", "payments", "invoices", "expenses"];

export function FinancePanel() {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // The sidebar deep-links tabs (?tab=folios / ?tab=expenses) so "Guest
  // folio" and "Expenses" are separate navigation entries on this shared
  // page. The URL stays in sync when switching tabs inside the page too,
  // keeping the sidebar's active state truthful.
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
    { key: "overview", label: t.finance.tabs.overview, icon: LayoutDashboard },
    { key: "folios", label: t.finance.tabs.folios, icon: FileText },
    { key: "payments", label: t.finance.tabs.payments, icon: Receipt },
    { key: "invoices", label: t.finance.tabs.invoices, icon: ReceiptText },
    { key: "expenses", label: t.finance.tabs.expenses, icon: PiggyBank },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={changeTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "folios" ? <FoliosTab /> : null}
      {tab === "payments" ? <PaymentsTab /> : null}
      {tab === "invoices" ? <InvoicesTab /> : null}
      {tab === "expenses" ? <ExpensesTab /> : null}
    </>
  );
}
