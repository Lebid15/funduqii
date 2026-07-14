import type { ReactNode } from "react";

import { formatDate, formatDateTime, formatMoney, reservationStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import type {
  Reservation,
  ReservationFinancialSummary,
  Stay,
} from "@/lib/api/types";

import {
  fxDirectionLabel,
  isForeignPayment,
  occupantPrintName,
  relationshipLabel,
} from "./reservationShared";

/** Real hotel identity + policies resolved from settings/profile (never
 * hard-coded). Every optional field is omitted from the printed header when
 * absent so the document never shows a broken placeholder or fake data. */
export interface ReservationPrintIdentity {
  name: string;
  logoUrl: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  /** Hotel-configured cancellation policy — printed ONLY when present. */
  cancellationPolicy: string | null;
  /** Hotel-configured important notes — printed ONLY when present. */
  importantNotes: string | null;
}

interface PrintRow {
  label: string;
  value: ReactNode;
}

/** A technical code (reservation no., phone, document no., FX rate) rendered
 * LTR + isolated so an Arabic RTL page never reorders its digits/segments. */
function Code({ children }: { children: ReactNode }) {
  return (
    <bdi dir="ltr" className="resv-print__code">
      {children}
    </bdi>
  );
}

/** Partially mask a document number for a printed sheet: keep only the last few
 * characters, hide the rest behind bullets. A value already masked server-side
 * (bullets, for callers without `guests.view_sensitive_data`) is returned as-is.
 * Never used on the national id — that field is never printed. */
function maskDocumentNumber(value: string): string {
  const v = value.trim();
  if (!v) return "";
  if (v.includes("•")) return v; // already masked by the backend
  const visible = 3;
  if (v.length <= visible) return "•".repeat(Math.max(2, v.length));
  return "•".repeat(Math.max(3, v.length - visible)) + v.slice(-visible);
}

/**
 * The formal, A4, RTL/LTR reservation-confirmation DOCUMENT (not a print of the
 * card/details). Pure presentation: it receives an already-fetched reservation,
 * the DERIVED backend financial summary (or null), the optional in-house stay
 * (for the actual check-in time), the resolved hotel identity and the caller's
 * money/sensitive-data permissions. Money renders from backend Decimal strings
 * via `formatMoney` — never recomputed, never parseFloat. Sensitive identity
 * (national id, father/mother name, date of birth, document images) is NEVER
 * printed; a document number is shown partially masked only with
 * `guests.view_sensitive_data`. The financial block is omitted honestly when the
 * caller lacks `finance.view` or the reservation is unpriced.
 */
export function ReservationPrintDocument({
  reservation,
  summary,
  identity,
  stay,
  checkoutTime,
  canViewMoney,
  canViewSensitive,
}: {
  reservation: Reservation;
  summary: ReservationFinancialSummary | null;
  identity: ReservationPrintIdentity;
  stay: Stay | null;
  checkoutTime: string | null;
  canViewMoney: boolean;
  canViewSensitive: boolean;
}) {
  const { t, locale } = useI18n();
  const p = t.reservations.print;
  const r = reservation;

  // Money is used ONLY when the caller may see it, the summary is viewable and
  // the reservation is priced — otherwise the whole financial section is left
  // off the sheet (honest-when-empty; zero-paid stays truthful).
  const money =
    canViewMoney &&
    summary !== null &&
    summary.can_view_money &&
    summary.is_priced !== false
      ? summary
      : null;

  const companions = r.occupants ?? [];
  const companionCount = r.occupants
    ? r.occupants.length
    : Math.max(0, r.adults - 1);
  const checkedIn = r.stay_status === "in_house" || r.has_in_house_stay;

  // ---- Header identity (from real settings/profile only) -------------------
  const contactBits = [identity.phone, identity.email].filter(Boolean);

  // ---- Guest section -------------------------------------------------------
  const guestRows: PrintRow[] = [
    { label: p.guestName, value: r.primary_guest_name || "—" },
  ];
  if (r.primary_guest_phone) {
    guestRows.push({ label: p.phone, value: <Code>{r.primary_guest_phone}</Code> });
  }
  if (r.primary_guest_nationality) {
    guestRows.push({ label: p.nationality, value: r.primary_guest_nationality });
  }
  if (r.primary_guest_email) {
    guestRows.push({ label: p.email, value: <Code>{r.primary_guest_email}</Code> });
  }
  if (r.primary_guest_document_type) {
    const docLabel =
      (t.guests.documentTypes as Record<string, string>)[
        r.primary_guest_document_type
      ] ?? r.primary_guest_document_type;
    guestRows.push({ label: p.documentType, value: docLabel });
    // A document number is shown partially masked ONLY to holders of
    // guests.view_sensitive_data; otherwise it is omitted entirely.
    if (canViewSensitive && r.primary_guest_document_number) {
      guestRows.push({
        label: p.documentNumber,
        value: <Code>{maskDocumentNumber(r.primary_guest_document_number)}</Code>,
      });
    }
  }

  // ---- Room & stay section -------------------------------------------------
  const roomLabels = r.lines.map((l) =>
    l.room_number ? l.room_number : `${l.room_type_name} ×${l.quantity}`,
  );
  const floorNames = Array.from(
    new Set(r.lines.map((l) => l.floor_name).filter((f): f is string => Boolean(f))),
  );
  const typeNames = Array.from(new Set(r.lines.map((l) => l.room_type_name)));

  const stayRows: PrintRow[] = [];
  if (roomLabels.length) {
    stayRows.push({ label: p.room, value: roomLabels.join(" · ") });
  }
  if (floorNames.length) {
    stayRows.push({ label: p.floor, value: floorNames.join(" · ") });
  }
  if (typeNames.length) {
    stayRows.push({ label: p.roomType, value: typeNames.join(" · ") });
  }
  stayRows.push({ label: p.checkIn, value: formatDate(r.check_in_date, locale) });
  if (r.expected_arrival_time) {
    stayRows.push({ label: p.arrivalTime, value: <Code>{r.expected_arrival_time}</Code> });
  }
  stayRows.push({ label: p.checkOut, value: formatDate(r.check_out_date, locale) });
  if (checkoutTime) {
    stayRows.push({ label: p.checkoutTime, value: <Code>{checkoutTime}</Code> });
  }
  stayRows.push({ label: p.nights, value: String(r.nights) });
  stayRows.push({ label: p.persons, value: String(r.total_guests) });
  stayRows.push({ label: p.adults, value: String(companionCount) });
  stayRows.push({ label: p.children, value: String(r.children) });
  if (checkedIn && stay?.actual_check_in_at) {
    stayRows.push({
      label: p.actualCheckIn,
      value: formatDateTime(stay.actual_check_in_at, locale),
    });
  }

  // ---- Financial section (derived, viewable, priced only) ------------------
  const financialRows: PrintRow[] = [];
  if (money) {
    if (money.nightly_rate) {
      financialRows.push({
        label: p.nightly,
        value: <bdi>{formatMoney(money.nightly_rate, money.currency, locale)}</bdi>,
      });
    }
    financialRows.push({ label: p.nights, value: String(money.nights) });
    if (money.reservation_total !== null) {
      financialRows.push({
        label: p.total,
        value: <bdi>{formatMoney(money.reservation_total, money.currency, locale)}</bdi>,
      });
    }
    // Zero-paid is truthful: paid renders as the currency's zero, remaining
    // stays the backend value — no phantom method/rate is invented.
    financialRows.push({
      label: p.paid,
      value: <bdi>{formatMoney(money.paid, money.currency, locale)}</bdi>,
    });
    if (money.remaining !== null) {
      financialRows.push({
        label: p.remaining,
        value: <bdi>{formatMoney(money.remaining, money.currency, locale)}</bdi>,
      });
    }
  }

  // ---- Notes & terms (only what actually exists) ---------------------------
  const reservationNote = [r.notes, r.special_requests].filter(Boolean).join(" · ");

  return (
    <article className="resv-print" aria-label={p.title}>
      {/* HEADER — real hotel identity */}
      <header className="resv-print__head">
        <div className="resv-print__brand">
          {identity.logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- print sheet needs a plain, unoptimized image
            <img
              src={identity.logoUrl}
              alt=""
              className="resv-print__logo"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = "none";
              }}
            />
          ) : null}
          <div className="resv-print__identity">
            <p className="resv-print__hotel-name">{identity.name}</p>
            {identity.address ? (
              <p className="resv-print__hotel-line">{identity.address}</p>
            ) : null}
            {contactBits.length ? (
              <p className="resv-print__hotel-line">
                {contactBits.map((bit, i) => (
                  <span key={i}>
                    {i > 0 ? " · " : ""}
                    <Code>{bit}</Code>
                  </span>
                ))}
              </p>
            ) : null}
          </div>
        </div>
        <div className="resv-print__docmeta">
          <p className="resv-print__doctitle">{p.title}</p>
          <p className="resv-print__docline">
            <span>{p.numberLabel}</span>{" "}
            <Code>{r.reservation_number}</Code>
          </p>
          <p className="resv-print__docline">
            <span>{p.issuedLabel}</span> {formatDateTime(r.created_at, locale)}
          </p>
          <p className="resv-print__docline">
            <span>{p.statusLabel}</span>{" "}
            <span className="resv-print__status">{reservationStatusLabel(r.status, t)}</span>
            {checkedIn ? (
              <span className="resv-print__status resv-print__status--in">{p.checkedIn}</span>
            ) : null}
          </p>
        </div>
      </header>

      {/* GUEST */}
      <section className="resv-print__section">
        <h3 className="resv-print__section-title">{p.sectionGuest}</h3>
        <dl className="resv-print__grid">
          {guestRows.map((row, i) => (
            <div className="resv-print__row" key={i}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ROOM & STAY */}
      <section className="resv-print__section">
        <h3 className="resv-print__section-title">{p.sectionStay}</h3>
        <dl className="resv-print__grid">
          {stayRows.map((row, i) => (
            <div className="resv-print__row" key={i}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* COMPANIONS (only when named companions exist) */}
      {companions.length > 0 ? (
        <section className="resv-print__section">
          <h3 className="resv-print__section-title">{p.sectionCompanions}</h3>
          <table className="resv-print__table">
            <thead>
              <tr>
                <th>{p.guestName}</th>
                <th>{t.reservations.wizard.companions.relationship}</th>
              </tr>
            </thead>
            <tbody>
              {companions.map((occ) => (
                <tr className="resv-print__row" key={occ.id}>
                  {/* First + last only — the printed slip omits the father name
                      (F2/§17), matching the primary guest's name policy. */}
                  <td>{occupantPrintName(occ, t)}</td>
                  <td>{relationshipLabel(occ.relationship, t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {/* FINANCIAL (derived, viewable, priced only) */}
      {money ? (
        <section className="resv-print__section">
          <h3 className="resv-print__section-title">{p.sectionFinancial}</h3>
          <dl className="resv-print__grid">
            {financialRows.map((row, i) => (
              <div className="resv-print__row" key={i}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
          {money.payments.length > 0 ? (
            <table className="resv-print__table resv-print__table--pay">
              <thead>
                <tr>
                  <th>{p.paymentMethod}</th>
                  <th>{p.paymentAmount}</th>
                  <th>{p.exchangeRate}</th>
                </tr>
              </thead>
              <tbody>
                {money.payments.map((payment) => {
                  const foreign = isForeignPayment(payment, money.currency);
                  return (
                    <tr className="resv-print__row" key={payment.id}>
                      <td>{t.finance.methods[payment.method]}</td>
                      <td>
                        <bdi>
                          {formatMoney(
                            payment.amount,
                            payment.currency || money.currency,
                            locale,
                          )}
                        </bdi>
                        {foreign ? (
                          <>
                            {" "}
                            <span className="resv-print__muted">
                              (
                              <bdi>
                                {formatMoney(
                                  payment.original_amount as string,
                                  payment.payment_currency,
                                  locale,
                                )}
                              </bdi>
                              )
                            </span>
                          </>
                        ) : null}
                      </td>
                      <td>
                        {foreign && payment.exchange_rate ? (
                          <span>
                            <Code>{payment.exchange_rate}</Code>{" "}
                            <span className="resv-print__muted">
                              {fxDirectionLabel(
                                payment.rate_basis,
                                t.reservations.wizard.booking,
                              )}
                            </span>
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : null}
        </section>
      ) : null}

      {/* NOTES & TERMS (only what exists) + a benign official instruction */}
      <section className="resv-print__section resv-print__section--notes">
        <h3 className="resv-print__section-title">{p.sectionNotes}</h3>
        {reservationNote ? (
          <p className="resv-print__note">
            <strong>{p.reservationNotes}:</strong> {reservationNote}
          </p>
        ) : null}
        {identity.cancellationPolicy ? (
          <p className="resv-print__note">
            <strong>{p.cancellationPolicy}:</strong> {identity.cancellationPolicy}
          </p>
        ) : null}
        {identity.importantNotes ? (
          <p className="resv-print__note">
            <strong>{p.importantNotes}:</strong> {identity.importantNotes}
          </p>
        ) : null}
        <p className="resv-print__note resv-print__note--official">{p.arrivalInstruction}</p>
      </section>

      {/* SIGNATURE / STAMP — restrained underlines */}
      <div className="resv-print__signatures">
        <div className="resv-print__sign">
          <span className="resv-print__sign-line" aria-hidden />
          <span className="resv-print__sign-label">{p.signatureFrontDesk}</span>
        </div>
        <div className="resv-print__sign">
          <span className="resv-print__sign-line" aria-hidden />
          <span className="resv-print__sign-label">{p.signatureGuest}</span>
        </div>
        <div className="resv-print__sign resv-print__sign--stamp">
          <span className="resv-print__stamp-box" aria-hidden />
          <span className="resv-print__sign-label">{p.hotelStamp}</span>
        </div>
      </div>

      {/* FOOTER — identity + print time only (no ids/paths/urls) */}
      <footer className="resv-print__foot">
        <span>{identity.name}</span>
        {contactBits.length ? (
          <span>
            {" · "}
            {contactBits.map((bit, i) => (
              <span key={i}>
                {i > 0 ? " · " : ""}
                <Code>{bit}</Code>
              </span>
            ))}
          </span>
        ) : null}
        <span className="resv-print__foot-print">
          {" · "}
          {p.printedOn} {formatDateTime(new Date().toISOString(), locale)}
        </span>
      </footer>
    </article>
  );
}
