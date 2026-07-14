"use client";

import { useCallback, useEffect, useState } from "react";
import { Printer, RotateCcw } from "lucide-react";

import { Alert, Button, LoadingState, Modal } from "@/components/ui";
import { getReservation, getReservationFinancialSummary } from "@/lib/api/reservations";
import { getSettings } from "@/lib/api/hotel";
import { getStay } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  HotelSettings,
  Reservation,
  ReservationFinancialSummary,
  Stay,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useHotelProfile } from "@/lib/session/HotelProfileContext";

import {
  ReservationPrintDocument,
  type ReservationPrintIdentity,
} from "./ReservationPrintDocument";

/**
 * The exported reservation PRINT PREVIEW modal (§23). It shows the dedicated A4
 * confirmation document roughly as it will print, with PRINT / CLOSE / RETRY.
 *
 * Printing is IDEMPOTENT: the modal only READS the saved reservation, its
 * derived financial summary, the hotel settings and (for an immediate check-in)
 * the stay — it never creates or duplicates anything. `window.print()` fires
 * against the isolated `.resv-print` document; the namespaced print CSS hides
 * all app chrome so only the sheet prints, and the preview buttons never appear
 * on paper.
 *
 * Data is fetched by id when the modal opens; a caller that already holds the
 * reservation (list card) passes it as a prop for an instant first paint, and
 * the success screen (FE-B) may pass a pre-fetched `financialSummary` too. The
 * financial block follows `finance.view`; no guest documents are ever printed.
 */
export function ReservationPrintPreview({
  open,
  reservation,
  financialSummary,
  onClose,
}: {
  open: boolean;
  reservation?: Reservation;
  financialSummary?: ReservationFinancialSummary | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const p = t.reservations.print;
  const profile = useHotelProfile();
  const access = useHotelAccess();
  // FAIL-CLOSED (F1): a printed customer document must never leak money/sensitive
  // fields when the access context is absent — a null context grants nothing. The
  // server also masks these; this is defense-in-depth on the printed slip.
  const can = (...codes: string[]) =>
    access !== null && !access.loading && access.can(...codes);

  const canViewMoney = can("finance.view");
  const canViewSensitive = can("guests.view_sensitive_data");
  const reservationId = reservation?.id ?? null;

  // The reservation shown by the sheet — starts from the caller's copy (instant
  // paint) and is upgraded to the freshly-fetched full record (occupants, latest
  // snapshot) when the fetch resolves.
  const [full, setFull] = useState<Reservation | null>(reservation ?? null);
  const [settings, setSettings] = useState<HotelSettings | null>(null);
  const [summary, setSummary] = useState<ReservationFinancialSummary | null>(
    financialSummary ?? null,
  );
  const [stay, setStay] = useState<Stay | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  // Reset to the caller's copy whenever the target reservation changes so a
  // stale sheet never lingers between prints.
  useEffect(() => {
    setFull(reservation ?? null);
    setSummary(financialSummary ?? null);
    setStay(null);
  }, [reservationId, reservation, financialSummary]);

  useEffect(() => {
    if (!open || reservationId === null) return;
    let active = true;
    setLoading(true);
    setError(null);

    // All reads — idempotent. The financial summary is fetched only when the
    // caller may see money and did not already supply it; the stay only for an
    // in-house (immediate) booking, to surface the actual check-in time.
    const wantSummary = canViewMoney && !financialSummary;
    (async () => {
      try {
        const reservationPromise = getReservation(reservationId);
        const settingsPromise = getSettings().catch(() => null);
        const summaryPromise = wantSummary
          ? getReservationFinancialSummary(reservationId).catch(() => null)
          : Promise.resolve(financialSummary ?? null);

        const [nextReservation, nextSettings, nextSummary] = await Promise.all([
          reservationPromise,
          settingsPromise,
          summaryPromise,
        ]);
        if (!active) return;
        setFull(nextReservation);
        setSettings(nextSettings);
        if (wantSummary) setSummary(nextSummary);

        // The stay is a soft, secondary read — only when the booking is in-house.
        if (
          (nextReservation.stay_status === "in_house" ||
            nextReservation.has_in_house_stay) &&
          nextReservation.stay_id !== null
        ) {
          getStay(nextReservation.stay_id)
            .then((s) => {
              if (active) setStay(s);
            })
            .catch(() => {
              /* the actual check-in time is simply omitted */
            });
        }
      } catch (err) {
        if (active) setError(messageForError(err, t));
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable enough; identity fetched by id + retry
  }, [open, reservationId, retryToken, canViewMoney, financialSummary]);

  const retry = useCallback(() => setRetryToken((n) => n + 1), []);

  const docReservation = full ?? reservation ?? null;

  const addressParts = settings
    ? [settings.address_line, settings.area, settings.city, settings.country]
    : [profile?.city ?? "", profile?.country ?? ""];
  const address = addressParts.filter(Boolean).join(", ") || null;

  const identity: ReservationPrintIdentity = {
    name:
      settings?.display_name ||
      settings?.legal_name ||
      profile?.display_name ||
      profile?.hotel.name ||
      p.title,
    logoUrl: profile?.logo?.url ?? null,
    address,
    phone: settings?.phone || settings?.whatsapp_number || null,
    email: settings?.email || null,
    cancellationPolicy: settings?.cancellation_policy || null,
    importantNotes: settings?.important_notes || null,
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={p.previewTitle}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <>
          <Button variant="ghost" icon={RotateCcw} onClick={retry} disabled={loading}>
            {p.retry}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
          <Button
            icon={Printer}
            onClick={() => window.print()}
            disabled={docReservation === null}
          >
            {p.action}
          </Button>
        </>
      }
    >
      {error ? (
        <Alert tone="error">
          {error}{" "}
          <button type="button" className="inline-link" onClick={retry}>
            {p.retry}
          </button>
        </Alert>
      ) : null}
      {docReservation === null ? (
        <LoadingState label={t.common.loading} />
      ) : (
        <div className="resv-print-frame">
          <ReservationPrintDocument
            reservation={docReservation}
            summary={summary}
            identity={identity}
            stay={stay}
            checkoutTime={settings?.check_out_time ?? null}
            canViewMoney={canViewMoney}
            canViewSensitive={canViewSensitive}
          />
        </div>
      )}
    </Modal>
  );
}
