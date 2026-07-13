"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarCheck, CalendarSearch, Plus } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { Button, PageHeader } from "@/components/ui";
import {
  AvailabilityTab,
  ReservationsTab,
} from "@/components/hotel/reservations";
import { useGlobalRefresh } from "@/lib/globalRefresh";
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

  useGlobalRefresh(useCallback(() => setRefreshKey((k) => k + 1), []));

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
          availability engine) so its filters, modals and the create signal
          survive; only the global refresh remounts it. */}
      <div style={{ display: surface === "availability" ? "none" : undefined }}>
        <ReservationsTab key={refreshKey} createSignal={createSignal} />
      </div>
      {surface === "availability" ? <AvailabilityTab key={refreshKey} /> : null}
    </PageContainer>
  );
}
