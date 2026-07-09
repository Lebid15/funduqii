"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChefHat, LayoutDashboard, ListOrdered, UtensilsCrossed } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BoardTab } from "./BoardTab";
import { CatalogTab } from "./CatalogTab";
import { OrdersTab } from "./OrdersTab";
import { OverviewTab } from "./OverviewTab";

const TAB_KEYS = ["overview", "catalog", "orders", "board"];

export function ServicesPanel() {
  const { t } = useI18n();
  // Deep-linkable initial tab (?tab=orders — the topbar quick actions):
  // read once on mount, tabs themselves stay local state as before.
  const requested = useSearchParams().get("tab");
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "overview",
  );

  const tabs: TabItem[] = [
    { key: "overview", label: t.services.tabs.overview, icon: LayoutDashboard },
    { key: "catalog", label: t.services.tabs.catalog, icon: UtensilsCrossed },
    { key: "orders", label: t.services.tabs.orders, icon: ListOrdered },
    { key: "board", label: t.services.tabs.board, icon: ChefHat },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "catalog" ? <CatalogTab /> : null}
      {tab === "orders" ? <OrdersTab /> : null}
      {tab === "board" ? <BoardTab /> : null}
    </>
  );
}
