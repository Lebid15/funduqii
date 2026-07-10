"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CalendarCheck,
  CalendarPlus,
  CalendarRange,
  CalendarSearch,
  CalendarX2,
  CheckCircle2,
  Clock3,
  Globe,
  Plus,
} from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { Button, PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  AvailabilityTab,
  ReservationSummaryCards,
  ReservationsTab,
} from "@/components/hotel/reservations";
import {
  RESERVATION_VIEWS,
  type ReservationView,
} from "@/components/hotel/reservations/reservationViews";
import { useGlobalRefresh } from "@/lib/globalRefresh";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

type PageTab = ReservationView | "availability";

const PAGE_TABS: PageTab[] = [...RESERVATION_VIEWS, "availability"];

/** Legacy deep-link tabs (sidebar/quick actions used ?tab=reservations and
 * the old overview) — they land on "all" so nothing breaks. */
function normalizeTab(requested: string | null): PageTab | null {
  if (!requested) return null;
  if (requested === "reservations" || requested === "overview") return "all";
  return PAGE_TABS.includes(requested as PageTab)
    ? (requested as PageTab)
    : null;
}

/**
 * Reservations console (owner reorg): reservations are BOOKINGS only —
 * creating, tracking, confirming, cancelling — never stays or check-in/out
 * (those live in the front desk). Seven filtered views + the availability
 * engine, clickable summary counters, and one clear "New Reservation"
 * button at the top.
 */
export default function ReservationsPage() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const v = t.reservations.views;

  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState<PageTab>(normalizeTab(requested) ?? "all");
  const [createSignal, setCreateSignal] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [countsReload, setCountsReload] = useState(0);

  // Follow tab deep-links even while mounted (quick actions from the topbar
  // or the rooms board while already on this page).
  useEffect(() => {
    const next = normalizeTab(requested);
    if (next) setTab(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);

  useGlobalRefresh(useCallback(() => setRefreshKey((k) => k + 1), []));

  const canCreate =
    access === null || (!access.loading && access.can("reservations.create"));

  function newReservation() {
    if (tab === "availability") setTab("all");
    setCreateSignal((s) => s + 1);
  }

  const tabs: TabItem[] = [
    { key: "all", label: v.tabs.all, icon: CalendarCheck },
    { key: "today", label: v.tabs.today, icon: CalendarPlus },
    { key: "website", label: v.tabs.website, icon: Globe },
    { key: "future", label: v.tabs.future, icon: CalendarRange },
    { key: "pending", label: v.tabs.pending, icon: Clock3 },
    { key: "confirmed", label: v.tabs.confirmed, icon: CheckCircle2 },
    { key: "closed", label: v.tabs.closed, icon: CalendarX2 },
    { key: "availability", label: t.reservations.tabs.availability, icon: CalendarSearch },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t.reservations.title}
        subtitle={v.subtitle}
        icon={CalendarRange}
        tone="indigo"
        actions={
          canCreate ? (
            <Button icon={Plus} anim="add" onClick={newReservation}>
              {v.newReservation}
            </Button>
          ) : undefined
        }
      />

      <ReservationSummaryCards
        active={tab === "availability" ? "all" : tab}
        onSelect={(view) => setTab(view)}
        reloadKey={refreshKey + countsReload}
      />

      <Tabs tabs={tabs} active={tab} onChange={(key) => setTab(key as PageTab)} />

      {/* The list stays MOUNTED across tab switches (hidden under the
          availability tab) so its filters, modal state and the create
          signal survive; only the global refresh remounts it. */}
      <div style={{ display: tab === "availability" ? "none" : undefined }}>
        <ReservationsTab
          key={refreshKey}
          view={tab === "availability" ? "all" : tab}
          createSignal={createSignal}
          onChanged={() => setCountsReload((c) => c + 1)}
        />
      </div>
      {tab === "availability" ? <AvailabilityTab key={refreshKey} /> : null}
    </PageContainer>
  );
}
