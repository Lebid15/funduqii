"use client";

import { useEffect, useState } from "react";

import { Badge, PrintDocumentLayout } from "@/components/ui";
import { PrintModal } from "@/components/hotel/finance/shared";
import { getFolioStatement } from "@/lib/api/finance";
import type { FolioStatement, Stay } from "@/lib/api/types";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * A4 print documents for the stay cycle (§43–§45), all built on the CENTRAL
 * {@link PrintModal} + {@link PrintDocumentLayout} (isolated `@media print`
 * CSS, @page A4) — never a raw dashboard print. Every document fetches the
 * folio statement server-side for the hotel identity + ledger totals; nothing
 * financial is recomputed on the client. Sensitive data (document images, full
 * national id, parent names, DB ids, internal URLs) is never printed.
 */

/** Fetch the folio statement while the modal is open; null until loaded. */
function useStatement(open: boolean, folioId: number | null) {
  const [data, setData] = useState<FolioStatement | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!open || folioId === null) {
      setData(null);
      setError(false);
      return;
    }
    let cancelled = false;
    setData(null);
    setError(false);
    getFolioStatement(folioId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, folioId]);
  return { data, error };
}

/**
 * Preliminary statement (before settlement) and final statement (after
 * departure, fully paid) — §43/§45. Same ledger content; the mode only changes
 * the title and the account-status line.
 */
export function StayStatementPrintModal({
  open,
  folioId,
  mode,
  onClose,
}: {
  open: boolean;
  folioId: number | null;
  mode: "preliminary" | "final";
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const p = t.frontDesk.print;
  const { data, error } = useStatement(open, folioId);
  const title = mode === "final" ? p.finalTitle : p.preliminaryTitle;

  return (
    <PrintModal open={open} title={title} onClose={onClose}>
      {error ? (
        <p className="muted">{p.error}</p>
      ) : !data ? (
        <p className="muted">{t.common.loading}</p>
      ) : (
        <PrintDocumentLayout
          hotelName={data.hotel.hotel_name}
          hotelAddress={data.hotel.address}
          hotelPhone={data.hotel.phone}
          docTitle={title}
          docNumber={data.folio.folio_number}
          meta={[
            {
              label: p.status,
              value:
                mode === "final"
                  ? p.fullyPaid
                  : t.finance.folioStatus[data.folio.status],
            },
            { label: p.guest, value: data.folio.customer_name || data.folio.guest_name || "—" },
            ...(data.stay
              ? [
                  { label: p.room, value: data.stay.room_number },
                  { label: p.checkIn, value: formatDate(data.stay.planned_check_in_date, locale) },
                  { label: p.checkOut, value: formatDate(data.stay.planned_check_out_date, locale) },
                ]
              : []),
            ...(data.folio.reservation_number
              ? [{ label: p.reservation, value: data.folio.reservation_number }]
              : []),
            { label: p.issued, value: formatDateTime(new Date().toISOString(), locale) },
          ]}
          totals={[
            { label: p.totalCharges, value: formatMoney(data.folio.balance.total_charges, data.folio.currency, locale) },
            { label: p.totalPaid, value: formatMoney(data.folio.balance.total_payments, data.folio.currency, locale) },
            { label: p.remaining, value: <strong>{formatMoney(data.folio.balance.balance, data.folio.currency, locale)}</strong> },
          ]}
          signatureLabel={p.guestSignature}
          footer={p.thanks}
        >
          <h4>{p.charges}</h4>
          {data.folio.charges.length === 0 ? (
            <p className="muted">{p.noCharges}</p>
          ) : (
            <table className="print-table">
              <thead>
                <tr>
                  <th>{p.description}</th>
                  <th>{p.type}</th>
                  <th>{p.date}</th>
                  <th>{p.amount}</th>
                </tr>
              </thead>
              <tbody>
                {data.folio.charges.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.description}
                      {c.status === "voided" ? <> <Badge tone="danger">{p.voided}</Badge></> : null}
                    </td>
                    <td>{t.finance.chargeTypes[c.type]}</td>
                    <td>{formatDate(c.charge_date, locale)}</td>
                    <td>{formatMoney(c.total_amount, data.folio.currency, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h4>{p.payments}</h4>
          {data.folio.payments.length === 0 ? (
            <p className="muted">{p.noPayments}</p>
          ) : (
            <table className="print-table">
              <thead>
                <tr>
                  <th>{p.receipt}</th>
                  <th>{p.method}</th>
                  <th>{p.date}</th>
                  <th>{p.amount}</th>
                </tr>
              </thead>
              <tbody>
                {data.folio.payments.map((pay) => (
                  <tr key={pay.id}>
                    <td>
                      {pay.receipt_number}
                      {pay.status === "voided" ? <> <Badge tone="danger">{p.voided}</Badge></> : null}
                    </td>
                    <td>{t.finance.methods[pay.method]}</td>
                    <td>{formatDate(pay.paid_at, locale)}</td>
                    <td>{formatMoney(pay.amount, data.folio.currency, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </PrintDocumentLayout>
      )}
    </PrintModal>
  );
}

/**
 * Stay registration card / notice printed on check-in (§45): a professional A4
 * welcome record with the hotel identity, guest, room & stay period, the actual
 * check-in time, and the opening deposit/balance. No sensitive identity data.
 */
export function StayRegistrationPrintModal({
  open,
  stay,
  folioId,
  onClose,
}: {
  open: boolean;
  stay: Stay | null;
  folioId: number | null;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const p = t.frontDesk.print;
  const { data, error } = useStatement(open, folioId);

  return (
    <PrintModal open={open} title={p.registrationTitle} onClose={onClose}>
      {error ? (
        <p className="muted">{p.error}</p>
      ) : !stay || !data ? (
        <p className="muted">{t.common.loading}</p>
      ) : (
        <PrintDocumentLayout
          hotelName={data.hotel.hotel_name}
          hotelAddress={data.hotel.address}
          hotelPhone={data.hotel.phone}
          docTitle={p.registrationTitle}
          docNumber={data.folio.folio_number}
          meta={[
            { label: p.guest, value: stay.primary_guest_name },
            { label: p.room, value: stay.room_number },
            { label: p.roomType, value: stay.room_type_name },
            { label: p.checkIn, value: formatDate(stay.planned_check_in_date, locale) },
            { label: p.checkOut, value: formatDate(stay.planned_check_out_date, locale) },
            { label: p.checkInTime, value: formatDateTime(stay.actual_check_in_at, locale) },
            ...(stay.reservation_number
              ? [{ label: p.reservation, value: stay.reservation_number }]
              : []),
          ]}
          totals={[
            { label: p.deposit, value: formatMoney(data.folio.balance.total_payments, data.folio.currency, locale) },
            { label: p.remaining, value: <strong>{formatMoney(data.folio.balance.balance, data.folio.currency, locale)}</strong> },
          ]}
          signatureLabel={p.guestSignature}
          footer={p.welcome}
        />
      )}
    </PrintModal>
  );
}
