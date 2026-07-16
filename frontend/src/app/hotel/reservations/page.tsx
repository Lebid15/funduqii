"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarCheck, CalendarSearch, Plus } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { Button, PageHeader } from "@/components/ui";
import {
  AvailabilityTab,
  ReservationsTab,
} from "@/components/hotel/reservations";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

type Surface = "list" | "availability";

/**
 * Reservations console (reservations rework): reservations are BOOKINGS only —
 * create, track, confirm, cancel — never stays or check-in/out (those live in
 * the front desk). One unified page for owner and staff (permissions differ):
 * the summary cards + supported filters + cards-first list live in the list
 * surface; the availability engine is a SECONDARY surface reachable from the
 * header, never competing with the primary flow.
 */
export default function ReservationsPage() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const v = t.reservations.views;

  const searchParams = useSearchParams();
  const search = searchParams.toString();
  const [surface, setSurface] = useState<Surface>("list");
  const [createSignal, setCreateSignal] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);

  // Deep-links: ?action=new/find act on the list, so ensure the list surface is
  // showing; ?tab=availability opens the availability engine directly.
  useEffect(() => {
    if (searchParams.get("action")) {
      setSurface("list");
      return;
    }
    if (searchParams.get("tab") === "availability") setSurface("availability");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the URL is the trigger
  }, [search]);

  // "Pull latest" without a button: bump a refresh signal when the operator
  // returns to this tab (replaces the removed global topbar refresh). The list
  // consumes it as a non-destructive REFETCH (no remount), so its filters,
  // pagination, open modals and the in-progress create/edit wizard all survive.
  // `visibilitychange` (not raw window focus) fires only on real tab-return /
  // minimize-restore, not on every trivial focus event.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") setRefreshKey((k) => k + 1);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const canCreate =
    access === null || (!access.loading && access.can("reservations.create"));

  function newReservation() {
    setSurface("list");
    setCreateSignal((s) => s + 1);
  }

  return (
    <PageContainer>
      <PageHeader
        title={t.reservations.title}
        subtitle={v.subtitle}
        actions={
          <>
            <Button
              variant="secondary"
              icon={surface === "availability" ? CalendarCheck : CalendarSearch}
              onClick={() => setSurface(surface === "availability" ? "list" : "availability")}
            >
              {surface === "availability" ? v.backToList : t.reservations.tabs.availability}
            </Button>
            {canCreate ? (
              <Button icon={Plus} onClick={newReservation}>
                {v.newReservation}
              </Button>
            ) : null}
          </>
        }
      />

      {/* The list stays MOUNTED across surface switches (hidden under the
          availability engine) so its filters, modals and the in-progress
          create/edit wizard survive; returning to the tab pulls the latest via a
          refresh signal WITHOUT remounting. The availability engine is an
          on-demand query (state lost on surface switch anyway); it is rendered
          without a remount key so an in-progress search survives a tab-return. */}
      <div style={{ display: surface === "availability" ? "none" : undefined }}>
        <ReservationsTab refreshSignal={refreshKey} createSignal={createSignal} />
      </div>
      {surface === "availability" ? <AvailabilityTab /> : null}
    </PageContainer>
  );
}
