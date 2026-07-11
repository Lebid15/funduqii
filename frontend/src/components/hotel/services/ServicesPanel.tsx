"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Armchair, ChefHat, LayoutDashboard, ListOrdered, UtensilsCrossed } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BoardTab } from "./BoardTab";
import { CatalogTab } from "./CatalogTab";
import { OrdersTab } from "./OrdersTab";
import { OverviewTab } from "./OverviewTab";
import { TablesTab } from "./TablesTab";

const TAB_KEYS = ["overview", "catalog", "tables", "orders", "board"];

export function ServicesPanel() {
  const { t } = useI18n();
  // Deep-linkable tab (?tab=orders — the topbar quick actions): initial
  // read + follow URL changes so a quick action fired while ALREADY on this
  // page still lands on its tab. Manual tab clicks stay local as before.
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "overview",
  );
  useEffect(() => {
    if (requested && TAB_KEYS.includes(requested)) setTab(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);

  const tabs: TabItem[] = [
    { key: "overview", label: t.services.tabs.overview, icon: LayoutDashboard },
    { key: "catalog", label: t.services.tabs.catalog, icon: UtensilsCrossed },
    { key: "tables", label: t.services.tabs.tables, icon: Armchair },
    { key: "orders", label: t.services.tabs.orders, icon: ListOrdered },
    { key: "board", label: t.services.tabs.board, icon: ChefHat },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "catalog" ? <CatalogTab /> : null}
      {tab === "tables" ? <TablesTab /> : null}
      {tab === "orders" ? <OrdersTab /> : null}
      {tab === "board" ? <BoardTab /> : null}
    </>
  );
}
