"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarCheck, CalendarSearch, LayoutDashboard } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  AvailabilityTab,
  OverviewTab,
  ReservationsTab,
} from "@/components/hotel/reservations";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Reservations console (Phase 6): the hotel's internal booking system and
 * availability engine. Bookings only — no check-in/out, no guest profiles, no
 * money. Availability and overbooking are decided on the backend.
 */
const TAB_KEYS = ["overview", "availability", "reservations"];

export default function ReservationsPage() {
  const { t } = useI18n();
  // Deep-linkable tab (?tab=reservations — the topbar quick actions): initial
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
    { key: "overview", label: t.reservations.tabs.overview, icon: LayoutDashboard },
    { key: "availability", label: t.reservations.tabs.availability, icon: CalendarSearch },
    { key: "reservations", label: t.reservations.tabs.reservations, icon: CalendarCheck },
  ];

  return (
    <PageContainer>
      <PageHeader title={t.reservations.title} subtitle={t.reservations.subtitle} />
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "availability" ? <AvailabilityTab /> : null}
      {tab === "reservations" ? <ReservationsTab /> : null}
    </PageContainer>
  );
}
