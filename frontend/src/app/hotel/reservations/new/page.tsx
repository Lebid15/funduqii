"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarCheck } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { EmptyState, LoadingState } from "@/components/ui";
import { ReservationFormShell } from "@/components/hotel/reservations/wizard";
import { createInitialDraft } from "@/components/hotel/reservations/wizard/useReservationDraft";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/**
 * CREATE reservation deep-link route (RESERVATIONS-FORM-UX-CORRECTION · F1). The
 * primary UX opens the wizard as a MODAL over the list; this route renders the
 * SAME `ReservationFormShell` modal standalone so `/hotel/reservations/new` still
 * resolves (close / save navigate back to the list via the shell's defaults). A
 * room pinned from the rooms board arrives as `?room=&room_type=` and seeds the
 * first booking line. Permission-gated by `reservations.create`; the backend
 * remains the authoritative guard.
 */
export default function NewReservationPage() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const searchParams = useSearchParams();
  const room = searchParams.get("room");
  const roomType = searchParams.get("room_type");

  const seed = useMemo(() => {
    if (!room || !roomType) return undefined;
    const draft = createInitialDraft();
    draft.booking.lines = [{ room_type: roomType, room, quantity: "1" }];
    draft.booking.selected_room_id = Number(room);
    return draft;
  }, [room, roomType]);

  if (access && access.loading) {
    return (
      <PageContainer>
        <LoadingState label={t.common.loading} />
      </PageContainer>
    );
  }

  const allowed = access === null || access.can("reservations.create");
  if (!allowed) {
    return (
      <PageContainer>
        <EmptyState
          title={t.reservations.views.noPermissionTitle}
          hint={t.reservations.views.noPermissionHint}
          icon={CalendarCheck}
        />
      </PageContainer>
    );
  }

  return <ReservationFormShell mode="create" initialDraft={seed} />;
}
