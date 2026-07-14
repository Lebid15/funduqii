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

import {
  ActionIconButton,
  Badge,
  Button,
  Icon,
  PaymentStatusBadge,
} from "@/components/ui";
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

import {
  arrivalFlag,
  reservationStatusIcon,
  sourceIcon,
  sourceTone,
} from "./reservationShared";

/**
 * One reservation as a VERTICAL, premium, equal-height grid card (§34–§38),
 * suited to 4-per-row on wide screens. It is split into clear BLOCKS of
 * separate mini-fields (never cramped touching lines):
 *   (1) Header — TWO rows (RESERVATION-CARD refinement §3/§4):
 *       • Row 1: STATUS badges ONLY — reservation status + a SEPARATE "Resident"
 *         stay badge (§17, never conflated with the reservation status) + source
 *         + the arrives-today/tomorrow/overdue flag + the public-cancel badge.
 *         Each concept is its OWN badge (status vs source vs arrival vs stay).
 *       • Row 2: the reservation NUMBER (focal, uniform position, opens details)
 *         with an explicit EYE + PRINTER icon control beside it.
 *   (2) Guest — initials avatar + name + phone.
 *   (3) Room — SEPARATE fields: floor · room number · room type.
 *   (4) Stay — SEPARATE fields: check-in · arrival time · check-out · departure
 *       time · nights · persons.
 *   (5) Financial summary — permission-gated (finance.view); honest when
 *       unpriced or when money is hidden. Payment status is a FILLED semantic
 *       PaymentStatusBadge (unpaid = red per §14). Money is rendered via
 *       formatMoney from the reservation's DERIVED decimal-string fields.
 *   (6) Notes — one truncated line, only when present.
 *   (7) Smart status-aware action grid (no "more" menu): documents, confirm,
 *       edit, cancel — each gated by its own permission. The documents button
 *       opens a DOCUMENTS-ONLY secure viewer (never the general details).
 * §36 sensitive fields (national id, father/mother names, DoB, document images,
 * full companion data, long FX detail, file paths) live in details only — never
 * on the card.
 */
export function ReservationCard({
  reservation: r,
  businessDate,
  checkoutTime = null,
  printLoading = false,
  onView,
  onPrint,
  onDocuments,
  onConfirm,
  onEdit,
  onCancel,
}: {
  reservation: Reservation;
  businessDate: string | null;
  /** Hotel-wide expected checkout time ("HH:MM[:SS]") from settings — one
   * list-level value shared by every card; null when unknown. */
  checkoutTime?: string | null;
  /** True while THIS card's print data is being prepared — drives the printer
   * icon's spinner and blocks a double-open (the preview owns the visible load). */
  printLoading?: boolean;
  onView: (r: Reservation) => void;
  onPrint: (r: Reservation) => void;
  /** Opens the DOCUMENTS-ONLY secure viewer for this reservation (§9) — a
   * separate flow from `onView` (general details). */
  onDocuments: (r: Reservation) => void;
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
  // from the reservation status (§17). No write operations belong to it here.
  const inHouse = r.stay_status === "in_house" || r.has_in_house_stay;
  const editable = r.status === "held" || r.status === "confirmed";

  // View + Print + Documents are READS (never a write permission for a write).
  const canView = can("reservations.view");
  // §9 — the "Documents" button appears ONLY when the caller may read docs AND
  // the reservation actually has at least one; the count rides on a badge.
  const docCount = r.document_count;
  const showDocs = can("reservation_documents.view") && docCount > 0;
  // Writes are suppressed once the guest is in-house (front-desk owns the stay).
  const canConfirm = r.status === "held" && !inHouse && can("reservations.confirm");
  const canEdit = editable && !inHouse && can("reservations.update");
  // RESERVATIONS-FINAL-CLOSURE §2 — cancel is hidden once the reservation has
  // produced ANY stay (in-house OR already checked-out); a departed booking must
  // not be re-cancelled. `stay_id` is the latest related stay of any status, so
  // `stay_id === null` means "never checked in". The backend enforces this too.
  const canCancel = editable && r.stay_id === null && can("reservations.cancel");
  // §10 — a status may resolve to zero bottom actions (e.g. cancelled/expired
  // with no documents, or an in-house booking); the grid is then omitted so no
  // empty gap is left behind.
  const hasBottomActions = showDocs || canConfirm || canEdit || canCancel;

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
      {/* 1) Header — two rows: status badges (row 1) then the number + explicit
          eye/printer controls (row 2, uniform position across all cards). */}
      <div className="res-card__header">
        {/* Row 1 — STATUS badges ONLY (each concept its own separate badge). */}
        <div className="res-card__status-row">
          <Badge
            tone={reservationStatusTone(r.status)}
            variant="filled"
            icon={reservationStatusIcon(r.status)}
          >
            {reservationStatusLabel(r.status, t)}
          </Badge>
          {inHouse ? (
            <Badge tone="info" variant="filled" icon={BedDouble}>
              {c.resident}
            </Badge>
          ) : null}
          <Badge tone={sourceTone(r.source)} icon={sourceIcon(r.source)}>
            {t.reservations.source[r.source] ?? r.source}
          </Badge>
          {flag ? (
            <Badge
              tone={flag.tone}
              variant={flag.kind === "tomorrow" ? "outline" : "soft"}
              icon={flag.icon}
            >
              {flag.label}
            </Badge>
          ) : null}
          {r.public_cancel_requested_at && (r.status === "held" || r.status === "confirmed") ? (
            <Badge tone="warning">{t.reservations.views.publicCancelBadge}</Badge>
          ) : null}
        </div>

        {/* Row 2 — the reservation NUMBER (focal; opens details) + explicit
            eye/printer controls. The number stays start-aligned and the controls
            end-aligned so their position is stable across every card. */}
        <div className="res-card__idrow">
          {canView ? (
            <button
              type="button"
              className="res-card__open"
              onClick={() => onView(r)}
              aria-label={`${c.openDetails} — ${r.reservation_number}`}
            >
              <span className="res-card__number">{r.reservation_number}</span>
            </button>
          ) : (
            <span className="res-card__number">{r.reservation_number}</span>
          )}
          {canView ? (
            <div className="res-card__idactions">
              <ActionIconButton
                icon={Eye}
                label={c.openDetails}
                tooltip={c.openDetails}
                size="sm"
                variant="ghost"
                onClick={() => onView(r)}
              />
              <ActionIconButton
                icon={Printer}
                label={c.printReservation}
                tooltip={c.printReservation}
                size="sm"
                variant="ghost"
                loading={printLoading}
                onClick={() => onPrint(r)}
              />
            </div>
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
          Money values are DERIVED decimal strings rendered via formatMoney;
          payment status is a FILLED semantic badge (unpaid = red, §14). */}
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
              {r.stay_id !== null ? (
                // §1 — after check-in the account lives on the stay's folio; a
                // reservation-level paid/remaining/status would compare the room
                // total to folio payments that include in-stay charges. Show the
                // "on folio" state instead (the real balance is in the details).
                <div className="res-card__money-item res-card__money-status">
                  <dt>{c.paymentLabel}</dt>
                  <dd>
                    <Badge tone="neutral">{c.onFolioAccount}</Badge>
                  </dd>
                </div>
              ) : (
                <>
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
                        <PaymentStatusBadge
                          status={r.payment_status}
                          labels={c.paymentStatus}
                        />
                      </dd>
                    </div>
                  ) : null}
                </>
              )}
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

      {/* 7) Smart status-aware action grid (§10, no overflow menu). View + Print
          now live in the header icons; the bottom row carries documents + the
          status-aware writes. "Documents" opens the DOCUMENTS-ONLY secure viewer
          (§9), never the general details. Omitted entirely when empty. */}
      {hasBottomActions ? (
        <div className="res-card__actions res-card__actions--grid">
          {showDocs ? (
            <Button
              variant="secondary"
              size="sm"
              icon={FileText}
              onClick={() => onDocuments(r)}
            >
              {c.documents}
              <Badge tone="neutral">{docCount}</Badge>
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
      ) : null}
    </article>
  );
}
