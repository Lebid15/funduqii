"use client";

import { useState } from "react";
import { FileText, LayoutDashboard, PiggyBank, Receipt, ReceiptText } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { OverviewTab } from "./OverviewTab";
import { FoliosTab } from "./FoliosTab";
import { PaymentsTab } from "./PaymentsTab";
import { InvoicesTab } from "./InvoicesTab";
import { ExpensesTab } from "./ExpensesTab";

export function FinancePanel() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

  const tabs: TabItem[] = [
    { key: "overview", label: t.finance.tabs.overview, icon: LayoutDashboard },
    { key: "folios", label: t.finance.tabs.folios, icon: FileText },
    { key: "payments", label: t.finance.tabs.payments, icon: Receipt },
    { key: "invoices", label: t.finance.tabs.invoices, icon: ReceiptText },
    { key: "expenses", label: t.finance.tabs.expenses, icon: PiggyBank },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "folios" ? <FoliosTab /> : null}
      {tab === "payments" ? <PaymentsTab /> : null}
      {tab === "invoices" ? <InvoicesTab /> : null}
      {tab === "expenses" ? <ExpensesTab /> : null}
    </>
  );
}
