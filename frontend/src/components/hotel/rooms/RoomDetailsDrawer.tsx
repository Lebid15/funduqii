"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { Button, Icon, Modal, StatusBadge } from "@/components/ui";
import type { RoomBoardRoom } from "@/lib/api/types";
import { formatCapacity, formatDate, formatMoney, roomStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { AmenityChips } from "./AmenityChips";
import {
  bookabilityIcon,
  bookabilityTone,
  buildRoomLinks,
  occupancyIcon,
  occupancyTone,
  occupancyVariant,
  operationalIcon,
  operationalTone,
  operationalVariant,
} from "./boardShared";

/** Full room details (owner spec) as a central Modal — identity, capacity,
 * operational + computed status, note, last change, current guest, upcoming
 * reservation, and the COMPLETE permission-aware action set. */
export function RoomDetailsDrawer({
  room,
  currency,
  onClose,
  onChangeStatus,
}: {
  room: RoomBoardRoom | null;
  /** Hotel currency from the board response — the single price source. */
  currency: string;
  onClose: () => void;
  onChangeStatus: (room: RoomBoardRoom) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const b = t.rooms.board;
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  if (!room) return null;
  const links = buildRoomLinks(room, t, can);
  const canStatus = can("rooms.status_update");

  const rows: Array<[string, string]> = [
    [b.detailFloor, room.floor_name],
    [b.detailType, room.room_type_name],
    // Capacity is shown as two explicit rows (never a raw "1–1" range).
    [b.detailBaseCapacity, formatCapacity(room.base_capacity, room.base_capacity, t, locale)],
    [b.detailMaxCapacity, formatCapacity(room.max_capacity, room.max_capacity, t, locale)],
    [b.operationalStatus, roomStatusLabel(room.operational_status, t)],
  ];
  if (room.base_rate) {
    rows.push([b.pricePerNight, formatMoney(room.base_rate, currency, locale)]);
  }
  if (room.status_note) rows.push([b.statusNote, room.status_note]);
  if (room.status_changed_at) {
    rows.push([b.lastStatusChange, formatDate(room.status_changed_at, locale)]);
  }
  if (room.current_stay) {
    rows.push([b.currentGuest, room.current_stay.guest_name]);
    rows.push([
      b.plannedCheckOut,
      `${formatDate(room.current_stay.planned_check_out_date, locale)}${
        room.current_stay.reservation_number
          ? ` · ${room.current_stay.reservation_number}`
          : ""
      }`,
    ]);
  }
  if (room.next_reservation) {
    rows.push([
      b.upcomingReservation,
      `${room.next_reservation.guest_name} · ${formatDate(room.next_reservation.check_in_date, locale)} – ${formatDate(room.next_reservation.check_out_date, locale)} · ${room.next_reservation.reservation_number}`,
    ]);
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`${b.roomDetails} — ${room.number}`}
      closeLabel={t.common.close}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="stack">
        {/* The three independent axes as central StatusBadges (§6.3): occupancy
         * + operational + the bookability badge from `available_now`. */}
        <div className="cluster">
          <StatusBadge
            tone={occupancyTone(room.occupancy_status)}
            variant={occupancyVariant(room.occupancy_status)}
            icon={occupancyIcon(room.occupancy_status)}
            label={t.rooms.occupancy[room.occupancy_status]}
          />
          <StatusBadge
            tone={operationalTone(room.operational_status)}
            variant={operationalVariant(room.operational_status)}
            icon={operationalIcon(room.operational_status)}
            label={b.status[room.operational_status]}
          />
          <StatusBadge
            tone={bookabilityTone(room.available_now)}
            variant="outline"
            icon={bookabilityIcon(room.available_now)}
            label={room.available_now ? b.bookableNow : b.notBookable}
          />
        </div>
        <dl className="room-op-details">
          {rows.map(([label, value]) => (
            <div key={label} className="room-op-details__row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {/* Full EFFECTIVE feature list (§6.1): the board `amenities` value is
         * already type defaults − exclusions + additions, so an excluded feature
         * is never shown. The card shows only the top few. */}
        <AmenityChips amenities={room.amenities} label={b.roomFeatures} />
        <div className="cluster">
          {links.map((link) => (
            <Link key={link.key} href={link.href} className="btn btn--secondary btn--sm">
              <Icon icon={link.icon} size="sm" />
              {link.label}
            </Link>
          ))}
          {canStatus ? (
            <Button
              variant="ghost"
              size="sm"
              icon={RefreshCw}
              onClick={() => onChangeStatus(room)}
            >
              {b.changeStatus}
            </Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
