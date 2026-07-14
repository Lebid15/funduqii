"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CalendarCheck } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { ReservationFormShell } from "@/components/hotel/reservations/wizard";
import {
  reservationToDraft,
  type ReservationDraft,
} from "@/components/hotel/reservations/wizard/useReservationDraft";
import {
  getReservation,
  getReservationFinancialSummary,
  listReservationDocuments,
} from "@/lib/api/reservations";
import { messageForError } from "@/lib/api/errors";
import type {
  Reservation,
  ReservationDocument,
  ReservationFinancialSummary,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/** Everything the edit shell needs, built once when the reservation loads so the
 * draft's stable occupant/document keys survive re-renders. */
interface EditData {
  reservation: Reservation;
  draft: ReservationDraft;
  financialSummary: ReservationFinancialSummary | null;
}

/**
 * EDIT reservation deep-link route (RESERVATIONS-FORM-UX-CORRECTION §33). The
 * primary UX opens this wizard as a MODAL over the list; this route renders the
 * SAME `ReservationFormShell` modal standalone so `/hotel/reservations/[id]/edit`
 * still resolves (close / save navigate back to the list via the shell's
 * defaults). It loads the reservation, its documents and its derived financial
 * summary IN PARALLEL, then hydrates the SAME wizard as create via
 * `reservationToDraft`: guest,
 * companions, children, dates/room, notes and the existing documents (shown "on
 * file", never re-staged). The financial summary is DISPLAY-only and threaded to
 * the shell separately (§31 — an old transaction is never an editable field).
 *
 * Documents and the financial summary are permission-gated reads that DEGRADE
 * gracefully (empty / hidden) so a desk without `reservation_documents.view` or
 * `finance.view` can still edit the reservation core; the reservation fetch is the
 * only hard dependency. The backend re-enforces every permission on save.
 */
export default function EditReservationPage() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const [data, setData] = useState<EditData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [reservation, documents, financialSummary] = await Promise.all([
        getReservation(id),
        // Supplementary reads: a missing permission must not block the edit.
        listReservationDocuments(id).catch(() => [] as ReservationDocument[]),
        getReservationFinancialSummary(id).catch(
          () => null as ReservationFinancialSummary | null,
        ),
      ]);
      setData({
        reservation,
        draft: reservationToDraft(reservation, { documents }),
        financialSummary,
      });
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    load();
  }, [load]);

  if (access && access.loading) {
    return (
      <PageContainer>
        <LoadingState label={t.common.loading} />
      </PageContainer>
    );
  }

  const allowed = access === null || access.can("reservations.update");
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

  if (loading) {
    return (
      <PageContainer>
        <LoadingState label={t.common.loading} />
      </PageContainer>
    );
  }

  if (error || !data) {
    return (
      <PageContainer>
        <ErrorState
          title={t.states.errorTitle}
          message={error ?? t.errors.generic}
          retryLabel={t.common.retry}
          onRetry={() => {
            setLoading(true);
            load();
          }}
        />
      </PageContainer>
    );
  }

  return (
    <ReservationFormShell
      mode="edit"
      reservation={data.reservation}
      initialDraft={data.draft}
      financialSummary={data.financialSummary}
    />
  );
}
