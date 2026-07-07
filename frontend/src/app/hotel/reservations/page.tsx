"use client";

import { useState } from "react";
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
export default function ReservationsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");

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
