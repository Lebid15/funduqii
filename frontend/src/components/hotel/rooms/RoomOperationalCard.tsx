"use client";

import Link from "next/link";
import { Eye, Pencil } from "lucide-react";

import { Badge, Button, Icon } from "@/components/ui";
import type { RoomBoardRoom } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { cx } from "@/lib/utils";

import { buildRoomLinks, displayStatusTone } from "./boardShared";

/** One room on the operational board (owner UX round): number in a clear
 * pill + status badge, the type right under it, the essentials, the
 * status-specific operational line, then ONE primary status action plus the
 * fixed «عرض» (drawer) and «تعديل» (edit modal) — all permission-aware. */
export function RoomOperationalCard({
  room,
  onDetails,
  onEdit,
}: {
  room: RoomBoardRoom;
  onDetails: (room: RoomBoardRoom) => void;
  onEdit: (room: RoomBoardRoom) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const b = t.rooms.board;
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const primary = buildRoomLinks(room, t, can).slice(0, 1);
  const canEdit = can("rooms.update");

  return (
    <article className={cx("room-op-card", `room-op-card--${room.display_status}`)}>
      <div className="room-op-card__head">
        <span className="room-op-card__id">
          <span className="room-op-card__number-badge">{room.number}</span>
          <span className="room-op-card__type">{room.room_type_name}</span>
        </span>
        <Badge tone={displayStatusTone(room.display_status)}>
          {b.status[room.display_status]}
        </Badge>
      </div>

      <div className="room-op-card__meta">
        <span>
          {room.floor_name} · {b.capacity}: {room.base_capacity}–{room.max_capacity}
          {room.base_rate ? ` · ${b.pricePerNight}: ${room.base_rate}` : ""}
        </span>
        {room.display_name ? <span>{room.display_name}</span> : null}
      </div>

      <OperationalLine room={room} locale={locale} />

      <div className="room-op-card__actions">
        {primary.map((link) => (
          <Link key={link.key} href={link.href} className="btn btn--secondary btn--sm">
            <Icon icon={link.icon} size="sm" />
            {link.label}
          </Link>
        ))}
        <Button variant="ghost" size="sm" icon={Eye} onClick={() => onDetails(room)}>
          {b.view}
        </Button>
        {canEdit ? (
          <Button variant="ghost" size="sm" icon={Pencil} onClick={() => onEdit(room)}>
            {t.common.edit}
          </Button>
        ) : null}
      </div>
    </article>
  );
}

/** The status-specific line: who is in, who is coming, or what is wrong. */
function OperationalLine({
  room,
  locale,
}: {
  room: RoomBoardRoom;
  locale: Parameters<typeof formatDate>[1];
}) {
  const { t } = useI18n();
  const b = t.rooms.board;

  if (room.display_status === "occupied" && room.current_stay) {
    return (
      <div className="room-op-card__line">
        <strong>
          {b.residentLabel}: {room.current_stay.guest_name}
        </strong>
        <span className="muted">
          {b.plannedCheckOut}: {formatDate(room.current_stay.planned_check_out_date, locale)}
          {room.current_stay.reservation_number
            ? ` · ${room.current_stay.reservation_number}`
            : ""}
        </span>
      </div>
    );
  }
  if (room.display_status === "reserved" && room.next_reservation) {
    return (
      <div className="room-op-card__line">
        <strong>
          {b.upcomingLabel}: {room.next_reservation.guest_name}
        </strong>
        <span className="muted">
          {formatDate(room.next_reservation.check_in_date, locale)} ←{" "}
          {formatDate(room.next_reservation.check_out_date, locale)} ·{" "}
          {room.next_reservation.reservation_number}
        </span>
      </div>
    );
  }

  const statusLine: Partial<Record<typeof room.display_status, string>> = {
    available: b.readyNow,
    dirty: b.dirtyLine,
    cleaning: b.cleaningLine,
    maintenance: b.maintenanceLine,
    out_of_service: b.oosLine,
  };
  return (
    <div className="room-op-card__line">
      <span className="muted">
        {statusLine[room.display_status] ?? b.status[room.display_status]}
      </span>
      {room.status_note ? <span>{room.status_note}</span> : null}
      {room.status_changed_at ? (
        <span className="muted">
          {b.lastStatusChange}: {formatDate(room.status_changed_at, locale)}
        </span>
      ) : null}
    </div>
  );
}
