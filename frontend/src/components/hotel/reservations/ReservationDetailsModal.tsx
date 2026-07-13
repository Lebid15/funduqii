"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BedDouble,
  CalendarRange,
  ClipboardList,
  DoorOpen,
  FileText,
  History,
  StickyNote,
  UserRound,
} from "lucide-react";

import { Alert, Badge, Button, Icon, Modal, SectionCard } from "@/components/ui";
import { getReservationLogs } from "@/lib/api/reservations";
import type { Reservation, ReservationStatusLogEntry } from "@/lib/api/types";
import {
  formatDate,
  formatDateTime,
  reservationStatusLabel,
  reservationStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { sourceIcon, sourceTone } from "./reservationShared";

/** Full reservation detail as a wide Modal drawer (reservations rework):
 * clear SECTIONS instead of tabs, each hidden when it has no data. Shows only
 * what the bookings backend actually stores — no amounts/folio, no uploads,
 * documents are the snapshot type + number only. */
export function ReservationDetailsModal({
  open,
  reservation,
  onClose,
  onEdit,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  reservation?: Reservation;
  onClose: () => void;
  onEdit: (r: Reservation) => void;
  onConfirm: (r: Reservation) => void;
  onCancel: (r: Reservation) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
  const [logs, setLogs] = useState<ReservationStatusLogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState(false);

  useEffect(() => {
    if (!open || !reservation) return;
    setLogsLoading(true);
    setLogsError(false);
    getReservationLogs(reservation.id)
      .then(setLogs)
      .catch(() => setLogsError(true))
      .finally(() => setLogsLoading(false));
  }, [open, reservation]);

  if (!reservation) return null;
  const r = reservation;
  const d = t.reservations.details;
  const editable = r.status === "held" || r.status === "confirmed";
  const inHouse = r.has_in_house_stay;
  const docLabel = (v: string) =>
    (t.guests.documentTypes as Record<string, string>)[v] ?? v;
  const creator = r.created_by_name ?? r.created_by;
  const hasDocs = r.primary_guest_document_type || r.primary_guest_document_number;
  const hasNotes = r.notes || r.special_requests;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${d.title} ${r.reservation_number}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
          {r.status === "confirmed" && can("stays.view") ? (
            <Link href="/hotel/front-desk?tab=arrivals" className="btn btn--ghost btn--sm">
              <Icon icon={DoorOpen} size="sm" />
              {t.reservations.views.frontDeskLink}
            </Link>
          ) : null}
          {editable && !inHouse && can("reservations.update") ? (
            <Button variant="ghost" onClick={() => onEdit(r)}>
              {d.edit}
            </Button>
          ) : null}
          {r.status === "held" && can("reservations.confirm") ? (
            <Button onClick={() => onConfirm(r)}>{d.confirm}</Button>
          ) : null}
          {editable && !inHouse && can("reservations.cancel") ? (
            <Button variant="danger" onClick={() => onCancel(r)}>
              {d.cancel}
            </Button>
          ) : null}
        </>
      }
    >
      <div className="stack">
        {inHouse ? <Alert tone="info">{t.reservations.views.inHouseNoCancel}</Alert> : null}
        {r.public_cancel_requested_at &&
        (r.status === "held" || r.status === "confirmed") ? (
          <Alert tone="warning">
            {d.publicCancelRequested} ({formatDate(r.public_cancel_requested_at, locale)})
            {r.public_cancel_reason ? ` — ${r.public_cancel_reason}` : ""}
          </Alert>
        ) : null}

        {/* Overview */}
        <SectionCard title={d.sectionOverview} icon={ClipboardList}>
          <div className="cluster">
            <Badge tone={reservationStatusTone(r.status)}>
              {reservationStatusLabel(r.status, t)}
            </Badge>
            <Badge tone={r.booking_kind === "instant" ? "success" : "info"}>
              {t.reservations.kind[r.booking_kind]}
            </Badge>
            <Badge tone={sourceTone(r.source)}>
              <Icon icon={sourceIcon(r.source)} size="sm" />
              {t.reservations.source[r.source]}
            </Badge>
          </div>
          <dl className="room-op-details">
            {creator ? (
              <div className="room-op-details__row">
                <dt>{d.createdBy}</dt>
                <dd>{creator}</dd>
              </div>
            ) : null}
            <div className="room-op-details__row">
              <dt>{t.common.createdAt}</dt>
              <dd>{formatDateTime(r.created_at, locale)}</dd>
            </div>
            <div className="room-op-details__row">
              <dt>{t.common.updatedAt}</dt>
              <dd>{formatDateTime(r.updated_at, locale)}</dd>
            </div>
          </dl>
        </SectionCard>

        {/* Stay */}
        <SectionCard title={d.sectionStay} icon={CalendarRange}>
          <dl className="room-op-details">
            <div className="room-op-details__row">
              <dt>{d.dates}</dt>
              <dd>
                {formatDate(r.check_in_date, locale)} → {formatDate(r.check_out_date, locale)}
              </dd>
            </div>
            {r.expected_arrival_time ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.arrivalTime}</dt>
                <dd>{r.expected_arrival_time}</dd>
              </div>
            ) : null}
            <div className="room-op-details__row">
              <dt>{d.nights}</dt>
              <dd>{r.nights}</dd>
            </div>
            <div className="room-op-details__row">
              <dt>{d.guests}</dt>
              <dd>{r.total_guests}</dd>
            </div>
            {r.expected_payment_method ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.expectedPayment}</dt>
                <dd>{t.reservations.expectedPayment[r.expected_payment_method]}</dd>
              </div>
            ) : null}
            {r.hold_expires_at ? (
              <div className="room-op-details__row">
                <dt>{d.holdExpires}</dt>
                <dd>{formatDateTime(r.hold_expires_at, locale)}</dd>
              </div>
            ) : null}
            {r.status === "cancelled" && r.cancellation_reason ? (
              <div className="room-op-details__row">
                <dt>{d.cancellationReason}</dt>
                <dd>{r.cancellation_reason}</dd>
              </div>
            ) : null}
          </dl>
          <div>
            <span className="res-detail__subhead">
              <Icon icon={BedDouble} size="sm" /> {d.rooms}
            </span>
            <ul className="mini-list">
              {r.lines.map((l) => (
                <li key={l.id} className="mini-list__row">
                  <span>
                    {l.room_type_name} <span className="muted">({l.room_type_code})</span>
                    {l.floor_name ? <span className="muted"> · {l.floor_name}</span> : null}
                  </span>
                  <span>
                    {l.room_number ? (
                      <Badge tone="info">
                        {d.room} {l.room_number}
                      </Badge>
                    ) : (
                      `× ${l.quantity}`
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </SectionCard>

        {/* Guest */}
        <SectionCard title={d.sectionGuest} icon={UserRound}>
          <dl className="room-op-details">
            <div className="room-op-details__row">
              <dt>{d.guest}</dt>
              <dd>{r.primary_guest_name}</dd>
            </div>
            {r.primary_guest_phone ? (
              <div className="room-op-details__row">
                <dt>{d.phone}</dt>
                <dd>{r.primary_guest_phone}</dd>
              </div>
            ) : null}
            {r.primary_guest_email ? (
              <div className="room-op-details__row">
                <dt>{d.email}</dt>
                <dd>{r.primary_guest_email}</dd>
              </div>
            ) : null}
            {r.primary_guest_nationality ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.nationality}</dt>
                <dd>{r.primary_guest_nationality}</dd>
              </div>
            ) : null}
          </dl>
        </SectionCard>

        {/* Documents — snapshot type + number ONLY (no uploads). */}
        {hasDocs ? (
          <SectionCard title={d.sectionDocuments} icon={FileText}>
            <dl className="room-op-details">
              {r.primary_guest_document_type ? (
                <div className="room-op-details__row">
                  <dt>{t.reservations.form.documentType}</dt>
                  <dd>{docLabel(r.primary_guest_document_type)}</dd>
                </div>
              ) : null}
              {r.primary_guest_document_number ? (
                <div className="room-op-details__row">
                  <dt>{t.reservations.form.documentNumber}</dt>
                  <dd>{r.primary_guest_document_number}</dd>
                </div>
              ) : null}
            </dl>
          </SectionCard>
        ) : null}

        {/* Notes */}
        {hasNotes ? (
          <SectionCard title={d.sectionNotes} icon={StickyNote}>
            {r.notes ? (
              <div>
                <span className="res-detail__subhead">{d.notes}</span>
                <p>{r.notes}</p>
              </div>
            ) : null}
            {r.special_requests ? (
              <div>
                <span className="res-detail__subhead">{d.specialRequests}</span>
                <p>{r.special_requests}</p>
              </div>
            ) : null}
          </SectionCard>
        ) : null}

        {/* Status log */}
        <SectionCard title={d.sectionStatusLog} icon={History}>
          {logsLoading ? (
            <p className="muted">{t.common.loading}</p>
          ) : logsError ? (
            <p className="muted">{d.logsError}</p>
          ) : logs.length === 0 ? (
            <p className="muted">{d.noHistory}</p>
          ) : (
            <ul className="mini-list">
              {logs.map((log, i) => (
                <li key={i} className="mini-list__row">
                  <span>
                    {log.previous_status ? `${log.previous_status} → ` : ""}
                    {log.new_status}
                    {log.note ? ` · ${log.note}` : ""}
                  </span>
                  <span className="muted">{formatDateTime(log.created_at, locale)}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </Modal>
  );
}
