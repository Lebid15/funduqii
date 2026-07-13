"use client";

import Link from "next/link";
import {
  BedDouble,
  Building2,
  CalendarRange,
  CheckCircle2,
  Eye,
  Moon,
  Pencil,
  Printer,
  Users,
  Wallet,
  XCircle,
} from "lucide-react";

import { Badge, Button, Icon } from "@/components/ui";
import type { Reservation } from "@/lib/api/types";
import {
  formatDate,
  initials,
  reservationStatusLabel,
  reservationStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { arrivalFlag, sourceIcon, sourceTone } from "./reservationShared";

/**
 * One reservation as an equal-height grid card (reservations rework) —
 * cards-first, mirroring the rooms operational card regions:
 *   (1) header: reservation number (focal, opens details) + status / source /
 *       arrival-flag / public-cancel badges;
 *   (2) guest: initials avatar + name + phone;
 *   (3) stay facts: room(s) + floor + type · dates + arrival time · nights ·
 *       guests, each with a unified icon accompanying the text;
 *   (4) an optional "expected payment" info chip (label only — NEVER an amount);
 *   (5) an optional truncated note;
 *   (6) actions: view / print / confirm / edit / cancel — shown DIRECTLY on the
 *       card (no overflow menu), permission- and state-aware. Reservations are
 *       BOOKINGS only: there is NO money on a card. Empty regions are hidden.
 */
export function ReservationCard({
  reservation: r,
  businessDate,
  onView,
  onPrint,
  onConfirm,
  onEdit,
  onCancel,
}: {
  reservation: Reservation;
  businessDate: string | null;
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
  const editable = r.status === "held" || r.status === "confirmed";
  const inHouse = r.has_in_house_stay;

  // View + Print are READS, gated by reservations.view; writes never use view.
  const canView = can("reservations.view");
  const canConfirm = r.status === "held" && can("reservations.confirm");
  const canEdit = editable && !inHouse && can("reservations.update");
  const canCancel = editable && !inHouse && can("reservations.cancel");

  // Room + floor summary from the read lines (may carry a specific room/floor).
  const roomLabels = r.lines.map((l) =>
    l.room_number ? `${t.reservations.details.room} ${l.room_number}` : `${l.room_type_name} ×${l.quantity}`,
  );
  const floorNames = Array.from(
    new Set(r.lines.map((l) => l.floor_name).filter((f): f is string => Boolean(f))),
  );
  const typeNames = Array.from(new Set(r.lines.map((l) => l.room_type_name)));
  const note = r.notes || r.special_requests;

  return (
    <article
      className={`res-card res-card--${r.status}`}
      aria-label={`${t.reservations.details.title} ${r.reservation_number}`}
    >
      {/* 1) Header — number (focal, opens details) + badges. */}
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

      {/* 3) Stay facts — each with a unified accompanying icon. */}
      <dl className="res-card__facts">
        {roomLabels.length > 0 ? (
          <div className="res-card__fact">
            <dt>
              <Icon icon={BedDouble} size="sm" />
              {t.reservations.details.rooms}
            </dt>
            <dd>{roomLabels.join(" · ")}</dd>
          </div>
        ) : null}
        {floorNames.length > 0 ? (
          <div className="res-card__fact">
            <dt>
              <Icon icon={Building2} size="sm" />
              {c.floor}
            </dt>
            <dd>{floorNames.join(" · ")}</dd>
          </div>
        ) : null}
        {typeNames.length > 0 ? (
          <div className="res-card__fact">
            <dt>
              <Icon icon={BedDouble} size="sm" />
              {t.reservations.form.roomType}
            </dt>
            <dd>{typeNames.join(" · ")}</dd>
          </div>
        ) : null}
        <div className="res-card__fact">
          <dt>
            <Icon icon={CalendarRange} size="sm" />
            {t.reservations.details.dates}
          </dt>
          <dd>
            {formatDate(r.check_in_date, locale)} → {formatDate(r.check_out_date, locale)}
            {r.expected_arrival_time ? (
              <span className="muted"> · {r.expected_arrival_time}</span>
            ) : null}
          </dd>
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
            {t.reservations.views.guestsCount}
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

      {/* 4) Expected payment — an INFO label only (no amount, no currency). */}
      {r.expected_payment_method ? (
        <span className="res-card__chip">
          <Icon icon={Wallet} size="sm" />
          {c.expected}: {t.reservations.expectedPayment[r.expected_payment_method]}
        </span>
      ) : null}

      {/* 5) Note summary — truncated, only when present. */}
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

      {/* 6) Actions — shown directly, permission- and state-aware; they wrap into
          a tidy row and start at a consistent position (margin-block-start:auto). */}
      <div className="res-card__actions">
        {canView ? (
          <Button variant="secondary" size="sm" icon={Eye} onClick={() => onView(r)}>
            {t.reservations.list.view}
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
