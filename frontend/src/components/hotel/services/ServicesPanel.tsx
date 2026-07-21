"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ListOrdered, UtensilsCrossed } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { CatalogTab } from "./CatalogTab";
import { OrdersTab } from "./OrdersTab";

// Simplification wave: the surface is collapsed to two tabs. Preparation board
// and table management are folded INTO Orders (a view mode + a modal); the
// Overview KPI dashboard is dropped from the surface. Old deep links to the
// removed tabs (?tab=overview|tables|board) resolve to Orders below.
const TAB_KEYS = ["orders", "catalog"];

export function ServicesPanel() {
  const { t } = useI18n();
  // Deep-linkable tab (?tab=orders — the topbar quick actions): initial read +
  // follow URL changes so a quick action fired while ALREADY on this page still
  // lands on its tab. Manual tab clicks stay local as before.
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "orders",
  );
  useEffect(() => {
    // A removed tab (overview/tables/board) is not in TAB_KEYS, so it falls
    // through to the Orders default and is never re-applied here.
    if (requested && TAB_KEYS.includes(requested)) setTab(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);

  const tabs: TabItem[] = [
    { key: "orders", label: t.services.tabs.orders, icon: ListOrdered },
    { key: "catalog", label: t.services.tabs.catalog, icon: UtensilsCrossed },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "orders" ? <OrdersTab /> : null}
      {tab === "catalog" ? <CatalogTab /> : null}
    </>
  );
}
