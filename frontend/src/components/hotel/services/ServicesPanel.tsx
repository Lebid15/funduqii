"use client";

import { useState } from "react";
import { ChefHat, LayoutDashboard, ListOrdered, UtensilsCrossed } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { BoardTab } from "./BoardTab";
import { CatalogTab } from "./CatalogTab";
import { OrdersTab } from "./OrdersTab";
import { OverviewTab } from "./OverviewTab";

export function ServicesPanel() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

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
