"use client";

import Link from "next/link";
import {
  BedDouble,
  Building2,
  CalendarRange,
  CheckCircle2,
  Clock,
  Eye,
  FileText,
  Moon,
  Pencil,
  Printer,
  Tag,
  Users,
  XCircle,
} from "lucide-react";

import { Badge, Button, Icon } from "@/components/ui";
import type { Reservation } from "@/lib/api/types";
import {
  formatDate,
  formatMoney,
  initials,
  reservationStatusLabel,
  reservationStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { arrivalFlag, paymentStatusTone, sourceIcon, sourceTone } from "./reservationShared";

/**
 * One reservation as a VERTICAL, premium, equal-height grid card (§34–§38),
 * suited to 4-per-row on wide screens. It is split into clear BLOCKS of
 * separate mini-fields (never cramped touching lines):
 *   (1) Header — reservation number (focal, opens details) + reservation status,
 *       source, a SEPARATE "Resident" stay badge (§25 — never conflated with the
 *       reservation status) and the arrives-today/tomorrow/overdue flag.
 *   (2) Guest — initials avatar + name + phone.
 *   (3) Room — SEPARATE fields: floor · room number · room type.
 *   (4) Stay — SEPARATE fields: check-in · arrival time · check-out · departure
 *       time · nights · persons.
 *   (5) Financial summary — permission-gated (finance.view); honest when
 *       unpriced or when money is hidden. Money is rendered via formatMoney from
 *       the reservation's DERIVED decimal-string fields (never parseFloat/Float).
 *   (6) Notes — one truncated line, only when present.
 *   (7) Smart status-aware action grid (no "more" menu), each gated by its own
 *       permission; a real "View documents" button.
 * §36 sensitive fields (national id, father/mother names, DoB, document images,
 * full companion data, long FX detail, file paths) live in details only — never
 * on the card.
 */
export function ReservationCard({
  reservation: r,
  businessDate,
  checkoutTime = null,
  onView,
  onPrint,
  onConfirm,
  onEdit,
  onCancel,
}: {
  reservation: Reservation;
  businessDate: string | null;
  /** Hotel-wide expected checkout time ("HH:MM[:SS]") from settings — one
   * list-level value shared by every card; null when unknown. */
  checkoutTime?: string | null;
  onView: (r: Reservation) => void;
  onPrint: (r: Reservation) => void;
  onConfirm: (r: Reservation) => void;
  onEdit: (r: Reservation) => void;
  onCancel: (r: Reservation) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
  const c = t.reservations.card;

  const flag = arrivalFlag(r.check_in_date, businessDate, r.status, r.has_in_house_stay, t);
  // A reservation that has STARTED as a stay is "resident" — a SEPARATE state
  // from the reservation status (§25). No write operations belong to it here.
  const inHouse = r.stay_status === "in_house" || r.has_in_house_stay;
  const editable = r.status === "held" || r.status === "confirmed";

  // View + Print + Documents are READS (never a write permission for a write).
  const canView = can("reservations.view");
  const canViewDocs = can("reservation_documents.view");
  // Writes are suppressed once the guest is in-house (front-desk owns the stay).
  const canConfirm = r.status === "held" && !inHouse && can("reservations.confirm");
  const canEdit = editable && !inHouse && can("reservations.update");
  const canCancel = editable && !inHouse && can("reservations.cancel");

  // Financial summary (§35) — gated by finance.view; the money fields come back
  // null when the caller may not see money, so hide the block honestly. When
  // priced money exists OR the room type is explicitly unpriced, show the well.
  const canMoney = can("finance.view");
  const hasMoney =
    r.reservation_total !== null ||
    r.paid !== null ||
    r.remaining !== null ||
    r.nightly_rate !== null;
  const showMoney = canMoney && (hasMoney || r.is_priced === false);
  // Render a DERIVED decimal-string as money; a null/unpriced field degrades to a
  // neutral placeholder rather than a fabricated zero.
  const money = (value: string | null) =>
    value !== null ? formatMoney(value, r.currency, locale) : "—";

  // Room facts from the read lines — each its own separate field (§35).
  const roomNumbers = Array.from(
    new Set(r.lines.map((l) => l.room_number).filter((n): n is string => Boolean(n))),
  );
  const floorNames = Array.from(
    new Set(r.lines.map((l) => l.floor_name).filter((f): f is string => Boolean(f))),
  );
  const typeNames = Array.from(new Set(r.lines.map((l) => l.room_type_name)));
  const departureTime = checkoutTime ? checkoutTime.slice(0, 5) : null;
  const note = r.notes || r.special_requests;

  return (
    <article
      className={`res-card res-card--${r.status}`}
      aria-label={`${t.reservations.details.title} ${r.reservation_number}`}
    >
      {/* 1) Header — number (focal, opens details) + status/source/stay/flag. */}
      <div className="res-card__header">
        <button
          type="button"
          className="res-card__open"
          onClick={() => onView(r)}
          aria-label={`${c.openDetails} — ${r.reservation_number}`}
        >
          <span className="res-card__number">{r.reservation_number}</span>
          <Icon icon={Eye} size="sm" className="res-card__open-cue" />
        </button>
        <div className="res-card__badges">
          <Badge tone={reservationStatusTone(r.status)}>
            {reservationStatusLabel(r.status, t)}
          </Badge>
          <Badge tone={sourceTone(r.source)}>
            <Icon icon={sourceIcon(r.source)} size="sm" />
            {t.reservations.source[r.source] ?? r.source}
          </Badge>
          {inHouse ? (
            <Badge tone="info">
              <Icon icon={BedDouble} size="sm" />
              {c.resident}
            </Badge>
          ) : null}
          {flag ? (
            <Badge tone={flag.tone}>
              <Icon icon={flag.icon} size="sm" />
              {flag.label}
            </Badge>
          ) : null}
          {r.public_cancel_requested_at && (r.status === "held" || r.status === "confirmed") ? (
            <Badge tone="warning">{t.reservations.views.publicCancelBadge}</Badge>
          ) : null}
        </div>
      </div>

      {/* 2) Guest — initials avatar + name + phone. */}
      <div className="res-card__guest">
        <span className="res-card__avatar" aria-hidden="true">
          {initials(r.primary_guest_name)}
        </span>
        <span className="res-card__guest-text">
          <span className="res-card__guest-name">{r.primary_guest_name}</span>
          {r.primary_guest_phone ? (
            <span className="muted">{r.primary_guest_phone}</span>
          ) : null}
        </span>
      </div>

      {/* 3) Room — SEPARATE fields: floor · room number · room type. */}
      <dl className="res-card__facts">
        <div className="res-card__fact">
          <dt>
            <Icon icon={Building2} size="sm" />
            {c.floor}
          </dt>
          <dd>{floorNames.length > 0 ? floorNames.join(" · ") : "—"}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={BedDouble} size="sm" />
            {t.reservations.details.room}
          </dt>
          <dd>{roomNumbers.length > 0 ? roomNumbers.join(" · ") : "—"}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={Tag} size="sm" />
            {t.reservations.form.roomType}
          </dt>
          <dd>{typeNames.length > 0 ? typeNames.join(" · ") : "—"}</dd>
        </div>
      </dl>

      {/* 4) Stay — SEPARATE fields: check-in · arrival · check-out · departure ·
          nights · persons. */}
      <dl className="res-card__facts">
        <div className="res-card__fact">
          <dt>
            <Icon icon={CalendarRange} size="sm" />
            {c.checkIn}
          </dt>
          <dd>{formatDate(r.check_in_date, locale)}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={Clock} size="sm" />
            {c.arrivalTime}
          </dt>
          <dd>{r.expected_arrival_time ?? "—"}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={CalendarRange} size="sm" />
            {c.checkOut}
          </dt>
          <dd>{formatDate(r.check_out_date, locale)}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={Clock} size="sm" />
            {c.departureTime}
          </dt>
          <dd>{departureTime ?? "—"}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={Moon} size="sm" />
            {t.reservations.details.nights}
          </dt>
          <dd>{r.nights}</dd>
        </div>
        <div className="res-card__fact">
          <dt>
            <Icon icon={Users} size="sm" />
            {c.persons}
          </dt>
          <dd>
            {r.total_guests}
            {r.children > 0 ? (
              <span className="muted">
                {" "}
                ·{" "}
                {c.adultsChildren
                  .replace("{adults}", String(r.adults))
                  .replace("{children}", String(r.children))}
              </span>
            ) : null}
          </dd>
        </div>
      </dl>

      {/* 5) Financial summary — permission-gated; honest when unpriced/hidden.
          Money values are DERIVED decimal strings rendered via formatMoney. */}
      {showMoney ? (
        <dl className="res-card__money">
          {r.is_priced === false ? (
            <div className="res-card__money-empty">{c.notPriced}</div>
          ) : (
            <>
              <div className="res-card__money-item">
                <dt>{c.nightly}</dt>
                <dd>{money(r.nightly_rate)}</dd>
              </div>
              <div className="res-card__money-item res-card__money-item--total">
                <dt>{c.total}</dt>
                <dd>{money(r.reservation_total)}</dd>
              </div>
              <div className="res-card__money-item">
                <dt>{c.paid}</dt>
                <dd>{money(r.paid)}</dd>
              </div>
              <div className="res-card__money-item">
                <dt>{c.remaining}</dt>
                <dd>{money(r.remaining)}</dd>
              </div>
              {r.payment_status ? (
                <div className="res-card__money-item res-card__money-status">
                  <dt>{c.paymentLabel}</dt>
                  <dd>
                    <Badge tone={paymentStatusTone(r.payment_status)}>
                      {c.paymentStatus[r.payment_status]}
                    </Badge>
                  </dd>
                </div>
              ) : null}
            </>
          )}
        </dl>
      ) : null}

      {/* 6) Note summary — truncated, only when present. */}
      {note ? <p className="res-card__note">{note}</p> : null}

      {/* Checked-in guard: dates/rooms are managed at the front desk. */}
      {inHouse ? (
        <p className="res-card__inhouse muted">
          {c.inHouseNote}{" "}
          <Link href="/hotel/front-desk?tab=current" className="inline-link">
            {t.reservations.views.frontDeskLink}
          </Link>
        </p>
      ) : null}

      {/* 7) Smart status-aware action grid (§38, no overflow menu). Reads for
          everyone permitted; writes disappear for closed / in-house bookings.
          "View documents" is a real, prominent secondary button (§37). */}
      <div className="res-card__actions res-card__actions--grid">
        {canView ? (
          <Button variant="secondary" size="sm" icon={Eye} onClick={() => onView(r)}>
            {t.reservations.list.view}
          </Button>
        ) : null}
        {canViewDocs ? (
          <Button variant="secondary" size="sm" icon={FileText} onClick={() => onView(r)}>
            {c.documents}
          </Button>
        ) : null}
        {canView ? (
          <Button variant="ghost" size="sm" icon={Printer} onClick={() => onPrint(r)}>
            {c.print}
          </Button>
        ) : null}
        {canConfirm ? (
          <Button size="sm" icon={CheckCircle2} onClick={() => onConfirm(r)}>
            {t.reservations.list.confirm}
          </Button>
        ) : null}
        {canEdit ? (
          <Button variant="ghost" size="sm" icon={Pencil} onClick={() => onEdit(r)}>
            {t.common.edit}
          </Button>
        ) : null}
        {canCancel ? (
          <Button variant="dangerSoft" size="sm" icon={XCircle} onClick={() => onCancel(r)}>
            {t.reservations.list.cancel}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
